
import os
import re
from urllib.parse import parse_qs, urlsplit

from scrape_all.downloader.adapters.base import (
    DownloadResult, HostAdapter, ProbeResult, size_from_range_headers,
)
from scrape_all.downloader.fsutil import sanitize_filename, url_token

# rule34video.com：流媒体源站第二家（KVS 架构）。页面流（零 API）：
#   打开   视频页服务端渲染下载区 a.tag_item_download，每档一条：
#         href = /get_file/...?v-acctoken=<短期token>&download=true&download_filename=真名
#         锚文本 "MP4 2160p"（360p 档 url 路径是 _360.mp4，文本仍带 p）
#   选档   文本解析分辨率，取最高且 <= 1080p 上限（_MAX_RES，2026-08-30 放量前
#         从 2160p 调低省流量）；全部超上限/认不出时保页面原序兜底（首行，
#         note 里带原始档位可见）
#   下载   点击锚点即 attachment 直链（download=true），浏览器下载器流式落盘
#         （最高档实测 449MB，绝不能走 blob 路径）；suggested 名 = download_filename
#   体积   get_file 302 跳跨域 CDN（boomio-cdn.com 等），视频页内 fetch 被 CORS 掐；
#         probe 的链路验证：点击收下载事件拿到最终直链 -> 立刻 cancel（0 正文流量）
#         -> 在最终 origin 停一个页，同源 Range:0-0 读 content-range 总长
#   会话   v-acctoken 与 PHPSESSID 绑定、页面每次渲染新发——href 绝不跨会话缓存，
#         每次重开视频页读新鲜链接；需要 stealth 会话（调用方开
#         DownloadEngine(stealth=True)，即 probe_downloader.py --stealth）
#
# 状态判定：http 404/410 -> dead；标题命中 CF 特征 -> unknown（挑战页，等人工）；
# 200 但下载区+播放器元素全无且有登录字样 -> needs_auth（登录墙：部分视频登录
# 后才可见，实测 311026 形态——正常视频页必有 <video>/player 元素，是判据）；
# 其余渲染不出 -> unknown（probe）/ failed（download）。该站匿名可下载多数视频，
# 登录墙个别帖，人工登录后 ero_links set 回 pending 重跑。
#
# 坑（playground 实测）：context.on("page") 不能当广告弹窗杀手用——new_page()
# 开的页也触发该事件，会把自家主页当场关掉（0.1s 内 page.close，goto 全挂）。

_SEL = "a.tag_item_download"
_MAX_RES = 1080
_GOTO_MS = 45000
_SEL_WAIT_MS = 20000
_SETTLE_MS = 1500
_EVENT_WAIT_MS = 60000        # 点击 -> 事件是即时的，不用按体积放大（save_as 不限时）
_RANGE_TIMEOUT_MS = 30000

_VIDEO_PATH_RE = re.compile(r"^/video/(\d+)")
_RES_RE = re.compile(r"(\d{3,4})\s*p", re.I)
_CHALLENGE_MARKS = ("Just a moment", "Attention Required",
                    "Verify you are human", "Enable JavaScript")

_ROWS_JS = """() => Array.from(document.querySelectorAll('a.tag_item_download'))
  .slice(0, 8)
  .map((a, i) => ({i, text: (a.innerText || '').trim(), href: a.href}))
  .filter(r => r.href)"""

# 登录墙判据：正常视频页必有 <video> 元素（实测正常页=1，登录墙页=0——墙页
# 会被占位容器顶替，占位 class 带 "player" 字样，子串选择器会误伤，只认 <video>）；
# 登录字样做佐证（页头导航匿名态也常带，只有 video=0 时才看它）
_GATE_JS = """() => ({
  video: document.querySelectorAll('video').length,
  login: /log ?in|sign in/i.test(document.body ? document.body.innerText : ''),
})"""

# 停页上的同源 Range:0-0：读完响应头立刻 abort，0 正文流量
_RANGE_JS = """async ({url, timeoutMs}) => {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const resp = await fetch(url, {credentials: "include", signal: ctrl.signal,
                                   headers: {Range: "bytes=0-0"}});
    const h = {};
    resp.headers.forEach((v, k) => h[k] = v);
    clearTimeout(timer);
    ctrl.abort();
    return {status: resp.status, headers: h};
  } catch (e) { return {status: 0, error: String(e)}; }
}"""


def parse_rule34_url(url: str) -> str | None:
  """/video/<id>/<slug>/ -> 视频 id；search / 分类页等非视频形态返回 None"""
  m = _VIDEO_PATH_RE.match(urlsplit(url).path)
  return m.group(1) if m else None


def row_resolution(text: str) -> int:
  """档位文本里的分辨率数字（'MP4 2160p' -> 2160）；认不出 -1"""
  m = _RES_RE.search(text or "")
  return int(m.group(1)) if m else -1


def pick_best_row(rows: list[dict], max_res: int = _MAX_RES) -> dict | None:
  """最高分辨率且 <= max_res 的档；同分保页面原序；全部超上限/认不出取首行
  兜底（上限是选档偏好不是硬墙，档位信息留在 note 里给编排层判）"""
  if not rows:
    return None
  ok = [(i, r) for i, r in enumerate(rows)
        if 0 < row_resolution(r.get("text", "")) <= max_res]
  if ok:
    return max(ok, key=lambda kv: (row_resolution(kv[1]["text"]), -kv[0]))[1]
  return rows[0]


def filename_from_href(href: str) -> str:
  """download_filename 查询参数是站点起的真名（比 URL 路径名可信）；
  没有时退 URL 路径 basename（KVS 路径带尾斜杠，先剥），再没有空串"""
  name = (parse_qs(urlsplit(href).query).get("download_filename") or [""])[0]
  return name or os.path.basename(urlsplit(href).path.rstrip("/")) or ""


def local_filename(row: dict, vid: str) -> str:
  """落盘名：download_filename 真名优先，缺档时 rule34_{vid}_{档位文本}"""
  name = filename_from_href(row.get("href") or "").strip()
  if name:
    return name
  return f"rule34_{vid}_{row.get('text') or 'video'}.mp4"


def is_wait_timeout(e: Exception) -> bool:
  """playwright / patchright 的 TimeoutError 不同类，按消息特征认（引擎无关）"""
  msg = str(e)
  return "Timeout" in msg or "timeout" in msg.lower()


class Rule34Adapter(HostAdapter):
  hosts = frozenset({"rule34video.com"})

  async def _open_video_page(self, engine, url: str):
    """开视频页等下载区渲染。commit 即返回（不赌 domcontentloaded——该站视频页
    重脚本，selector 等待才是稳的），返回 (page, http_status)；调用方负责 close。"""
    page = await engine.context.new_page()
    resp = await page.goto(url, wait_until="commit", timeout=_GOTO_MS)
    try:
      await page.wait_for_selector(_SEL, timeout=_SEL_WAIT_MS)
    except Exception as e:
      if not is_wait_timeout(e):
        raise
    await page.wait_for_timeout(_SETTLE_MS)
    return page, (resp.status if resp else None)

  async def _rows(self, page) -> list[dict]:
    try:
      return await page.evaluate(_ROWS_JS)
    except Exception:
      return []

  async def _challenge_mark(self, page) -> str | None:
    """标题里的 CF 挑战页特征；认不出/读不到返回 None"""
    try:
      title = (await page.title()).lower()
    except Exception:
      return None
    return next((m for m in _CHALLENGE_MARKS if m.lower() in title), None)

  async def _login_gated(self, page) -> bool:
    """登录墙：200 但无 <video> 元素 + 登录字样（个别视频登录后才可见）"""
    try:
      gate = await page.evaluate(_GATE_JS)
    except Exception:
      return False
    return gate.get("video", 0) == 0 and bool(gate.get("login"))

  async def _click_row(self, page, index: int):
    """点第 index 档锚点收下载事件（attachment 直链，事件即时）。跨引擎
    TimeoutError 交给调用方按消息特征兜底。"""
    async with page.expect_download(timeout=_EVENT_WAIT_MS) as dl_info:
      await page.locator(_SEL).nth(index).click()
    return await dl_info.value

  async def _cdn_size(self, engine, final_url: str) -> tuple[int | None, str]:
    """(字节, note)：在最终直链的 origin 停页，同源 Range:0-0 读总长。
    get_file 302 的跨域 CDN 在视频页内 fetch 会被 CORS 掐，只有停到目标
    origin 才同源。任何失败返回 (None, note)，不挡主流程。"""
    parts = urlsplit(final_url or "")
    if not parts.netloc:
      return None, "无最终直链"
    park = await engine.context.new_page()
    try:
      await park.goto(f"{parts.scheme}://{parts.netloc}/",
                      wait_until="commit", timeout=20000)
      await park.evaluate("window.stop()")
      out = await park.evaluate(_RANGE_JS,
                                {"url": final_url, "timeoutMs": _RANGE_TIMEOUT_MS})
    except Exception as e:
      return None, f"停页探体积失败 {str(e)[:50]}"
    finally:
      await park.close()
    status = out.get("status")
    if status not in (200, 206):
      return None, f"cdn http {status} {parts.netloc}"
    return size_from_range_headers(out.get("headers", {})), \
        f"cdn {status} {parts.netloc}"

  def _best_note(self, best: dict, rows: list[dict]) -> str:
    quals = "/".join(r.get("text", "?") for r in rows)
    note = f"{len(rows)} 档[{quals}] 取 {best.get('text') or '?'}"
    if row_resolution(best.get("text", "")) > _MAX_RES:
      note += f"（超{_MAX_RES}p上限兜底首档）"
    return note

  async def probe(self, engine, url: str) -> ProbeResult:
    vid = parse_rule34_url(url)
    if not vid:
      return ProbeResult("unknown", note=f"非视频页形态: {url}")
    async with engine.slot():
      try:
        page, status = await self._open_video_page(engine, url)
      except Exception as e:
        return ProbeResult("unknown", note=str(e)[:120])
      try:
        rows = await self._rows(page)
        if not rows:
          if status in (404, 410):
            return ProbeResult("dead", note=f"http {status}")
          mark = await self._challenge_mark(page)
          if mark:
            return ProbeResult("unknown", note=f"疑似挑战页（{mark}），等人工")
          if await self._login_gated(page):
            return ProbeResult("needs_auth", note="登录墙：登录后才可见，人工登录后重跑")
          title = await page.title()
          return ProbeResult(
              "unknown", note=f"无下载区 http {status or '?'} title={title[:40]}")
        best = pick_best_row(rows)
        note = f"{vid} {self._best_note(best, rows)}"
        # 链路真章（0 正文流量）：点击收事件拿最终直链 -> 立刻 cancel ->
        # 最终 origin 停页探体积。失败不翻 alive，只进 note
        size, extra = None, ""
        try:
          dl = await self._click_row(page, best["i"])
          final_url = dl.url
          await dl.cancel()
          size, extra = await self._cdn_size(engine, final_url)
        except Exception as e:
          extra = f"链路验证失败 {str(e)[:60]}"
        return ProbeResult("alive", filename=sanitize_filename(
            local_filename(best, vid)), size=size, note=f"{note} {extra}".strip())
      finally:
        await page.close()

  async def download(self, engine, url: str, dest_dir: str) -> DownloadResult:
    vid = parse_rule34_url(url)
    if not vid:
      return DownloadResult("failed", note=f"非视频页形态: {url}")
    async with engine.slot():
      try:
        page, status = await self._open_video_page(engine, url)
      except Exception as e:
        return DownloadResult("failed", note=str(e)[:120])
      try:
        rows = await self._rows(page)
        if not rows:
          if status in (404, 410):
            return DownloadResult("dead", note=f"http {status}")
          mark = await self._challenge_mark(page)
          if mark:
            return DownloadResult("failed", note=f"疑似挑战页（{mark}）")
          if await self._login_gated(page):
            return DownloadResult("manual", note="登录墙：人工登录后 set 回 pending 重跑")
          return DownloadResult("failed", note=f"无下载区 http {status or '?'}")
        best = pick_best_row(rows)
        if not (best.get("href") or "").startswith("http"):
          return DownloadResult("failed", note=f"href 缺失: {best!r}")

        # 幂等：真名先算好（download_filename 每次渲染新发，但真名稳定），
        # 已存在就不点按钮（0 流量）；并发撞名由引擎落 {stem}.{token}{ext} 第二把
        name = sanitize_filename(local_filename(best, vid))
        dest = os.path.join(dest_dir, name)
        if os.path.exists(dest):
          return DownloadResult("skipped", path=dest,
                                size=os.path.getsize(dest), note="已存在")

        os.makedirs(dest_dir, exist_ok=True)
        try:
          download = await self._click_row(page, best["i"])
        except Exception as e:
          if is_wait_timeout(e):
            return DownloadResult(
                "failed", note=f"点击后无下载事件 {best.get('text') or ''}".strip())
          raise
        # 落盘走引擎收口（save_as 不限时，浏览器下载器流式写盘）
        dest = await engine.save_download(download, dest_dir, name, url_token(url))
        return DownloadResult("downloaded", path=dest, size=os.path.getsize(dest),
                              note=f"{best.get('text') or ''}".strip())
      finally:
        await page.close()
