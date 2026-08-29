
import asyncio
import contextlib
import os
from urllib.parse import urlsplit

from playwright.async_api import Page

from scrape_all.browser.session import BrowserSession
from scrape_all.downloader.fsutil import sanitize_filename

# 下载引擎：所有取回动作都发生在浏览器页面里——真实 Chrome TLS 指纹、
# browser_session/ 持久 profile 的登录态、走 DOWNLOADER_PROXY 的代理出口，
# 不暴露 python http 客户端指纹（防爬虫拉黑 / CF 挑战，与 cangku 取图同一套思路）。
#
# 页内 fetch 有同源约束，且 fetch 本身不下盘，所以提供三种原语（adapter 按家选）：
#   probe_headers   同源页内 fetch + Range:0-0，读到响应头立刻 abort —— 只探元信息不下数据
#   blob_download   同源页内 fetch 整文件进 blob -> <a download> 触发浏览器下载事件
#                   -> save_as 落盘。中小文件用（几百 MB 级会占渲染进程内存，别用）
#   direct_download 带下载事件期望的 goto —— 依赖服务端 Content-Disposition: attachment，
#                   浏览器下载器自己流式落盘，大文件用这个
#
# park 机制：先 goto(url, wait_until="commit") 拿到目标 origin 的页面、立刻
# window.stop() 掐掉正文流（不然 inline 渲染的视频会白吞一份流量），之后页内
# 同源 fetch 想取几次取几次。
#
# 并发：全局信号量限在飞行取回数（默认 1 串行）；同一 origin 的页操作再加页级
# 锁——一个页面上交错 evaluate 会互相踩，并发放开时也不许共享页。

DEFAULT_TIMEOUT_S = 120.0


class DownloadError(RuntimeError):
  pass


class DownloadEngine:
  def __init__(self, proxy_server: str = None, concurrency: int = 1,
               stealth: bool = False):
    """stealth=True 改用 patchright 会话（同 profile 同代理，API 兼容）：
    间歇性吃 CF 挑战的站点（如流媒体源站）用，普通文件托管不需要。"""
    self._proxy = proxy_server
    self._stealth = stealth
    self._sem = asyncio.Semaphore(concurrency)
    self._session: BrowserSession = None
    self._pages: dict[str, Page] = {}       # origin host -> parked page
    self._page_locks: dict[str, asyncio.Lock] = {}

  async def __aenter__(self) -> "DownloadEngine":
    self._session = BrowserSession(self._proxy, stealth=self._stealth)
    await self._session.__aenter__()
    return self

  async def __aexit__(self, exc_type, exc, tb):
    for page in self._pages.values():
      try:
        await page.close()
      except Exception:
        pass
    await self._session.__aexit__(exc_type, exc, tb)

  @property
  def context(self):
    """浏览器上下文（登录保证等场景直接用）"""
    return self._session.context

  @contextlib.asynccontextmanager
  async def slot(self):
    """adapter 的整页浏览+点击流程（不走 park 页原语）：一样要过并发闸"""
    async with self._sem:
      yield

  async def _page_for(self, url: str,
                      park_url: str = None) -> tuple[Page, asyncio.Lock]:
    """拿一个停在 url 所在 origin 的页（复用），以及该页的操作锁。
    park_url：目标 URL 自己没法当落点时（比如是 attachment，goto 会变成下载
    事件而 commit 不来），指定停在该 origin 的一个普通页面（如站点根）"""
    origin = urlsplit(url).netloc
    if origin not in self._pages:
      page = await self._session.new_page()
      try:
        # commit 即返回（重定向跟完后才算 commit），正文流立刻掐掉
        await page.goto(park_url or url, wait_until="commit")
        await page.evaluate("window.stop()")
      except Exception as e:
        await page.close()
        raise DownloadError(f"park 失败 {origin}: {e}")
      self._pages[origin] = page
      self._page_locks[origin] = asyncio.Lock()
    return self._pages[origin], self._page_locks[origin]

  async def probe_headers(self, url: str, timeout_s: float = 30.0,
                          park_url: str = None) -> dict:
    """同源页内探活：Range:0-0 请求，返回 {status, headers{}}；网络层出错 status=0"""
    async with self._sem:
      page, lock = await self._page_for(url, park_url)
      async with lock:
        return await page.evaluate(
            """async ({url, timeoutMs}) => {
              const ctrl = new AbortController();
              const timer = setTimeout(() => ctrl.abort(), timeoutMs);
              try {
                const resp = await fetch(url, {
                  credentials: "include", signal: ctrl.signal,
                  headers: {Range: "bytes=0-0"},
                });
                const h = {};
                resp.headers.forEach((v, k) => h[k] = v);
                const out = {status: resp.status, headers: h};
                clearTimeout(timer);
                ctrl.abort();   // 只要头，正文一字节都不要
                return out;
              } catch (e) { return {status: 0, error: String(e)}; }
            }""", {"url": url, "timeoutMs": int(timeout_s * 1000)})

  async def fetch_json(self, url: str, timeout_s: float = 30.0,
                       park_url: str = None) -> dict:
    """同源页内 fetch JSON（各家 API：pixeldrain / gofile 等）。
    不抛 HTTP 错：成功 {status, body}，非 2xx {status, body:null}，
    网络层失败 {status: 0, error}——调用方按状态码分流 dead/unknown"""
    async with self._sem:
      page, lock = await self._page_for(url, park_url)
      async with lock:
        return await page.evaluate(
            """async ({url, timeoutMs}) => {
              const ctrl = new AbortController();
              const timer = setTimeout(() => ctrl.abort(), timeoutMs);
              try {
                const resp = await fetch(url, {credentials: "include",
                                               headers: {Accept: "application/json"},
                                               signal: ctrl.signal});
                if (!resp.ok) return {status: resp.status, body: null};
                const body = await resp.json();
                clearTimeout(timer);
                return {status: resp.status, body};
              } catch (e) { return {status: 0, error: String(e)}; }
            }""", {"url": url, "timeoutMs": int(timeout_s * 1000)})

  async def blob_download(self, url: str, dest_dir: str,
                          filename: str = None,
                          timeout_s: float = DEFAULT_TIMEOUT_S,
                          park_url: str = None) -> str:
    """同源页内取整文件 -> 浏览器下载事件 -> save_as。返回落盘路径"""
    os.makedirs(dest_dir, exist_ok=True)
    fallback_name = filename or os.path.basename(urlsplit(url).path) or "unnamed"
    async with self._sem:
      page, lock = await self._page_for(url, park_url)
      async with lock:
        async with page.expect_download(timeout=timeout_s * 1000) as dl_info:
          err = await page.evaluate(
              """async ({url, name, timeoutMs}) => {
                const ctrl = new AbortController();
                const timer = setTimeout(() => ctrl.abort(), timeoutMs);
                try {
                  const resp = await fetch(url, {credentials: "include",
                                                 signal: ctrl.signal});
                  if (!resp.ok) return "HTTP " + resp.status;
                  const blob = await resp.blob();
                  clearTimeout(timer);
                  const a = document.createElement("a");
                  a.href = URL.createObjectURL(blob);
                  a.download = name;
                  document.body.appendChild(a);
                  a.click();
                  a.remove();
                  return "";
                } catch (e) { return String(e); }
              }""", {"url": url, "name": fallback_name,
                     "timeoutMs": int(timeout_s * 1000)})
          if err:
            # 在 with 里抛，expect_download 的等待才会立刻取消而不是干等到超时
            raise DownloadError(f"页内 fetch 失败 {err}: {url}")
        download = await dl_info.value
        dest = os.path.join(
            dest_dir, sanitize_filename(download.suggested_filename or fallback_name))
        await download.save_as(dest)
        return dest

  async def direct_download(self, url: str, dest_dir: str,
                            filename: str = None,
                            timeout_s: float = DEFAULT_TIMEOUT_S) -> str:
    """goto 触发浏览器下载（服务端须给 Content-Disposition: attachment）。
    大文件路径：浏览器下载器自己流式落盘，不占渲染进程内存。"""
    os.makedirs(dest_dir, exist_ok=True)
    fallback_name = filename or os.path.basename(urlsplit(url).path) or "unnamed"
    async with self._sem:
      # attachment URL 不能拿去 park（commit 不会来，来的就是下载事件），
      # 没停过页就开个裸页专门触发
      origin = urlsplit(url).netloc
      if origin in self._pages:
        page, lock = self._pages[origin], self._page_locks[origin]
      else:
        page = await self._session.new_page()
        lock = asyncio.Lock()
        self._pages[origin] = page
        self._page_locks[origin] = lock
      async with lock:
        async with page.expect_download(timeout=timeout_s * 1000) as dl_info:
          try:
            await page.goto(url)
          except Exception as e:
            # 导航被下载事件掐断时 goto 会抛 ERR_ABORTED——这正是期望路径，
            # 吞掉等 expect_download 收到下载；真没下载事件则超时暴露
            if "ERR_ABORTED" not in str(e):
              raise
        download = await dl_info.value
        # adapter 显式给的名字（probe 解析出的真名）优先，重跑幂等靠它对上
        dest = os.path.join(
            dest_dir,
            sanitize_filename(filename or download.suggested_filename
                              or fallback_name))
        await download.save_as(dest)
        return dest
