
import os
import re
from urllib.parse import parse_qs, urlsplit

from playwright.async_api import TimeoutError as PWTimeoutError

from scrape_all.downloader.adapters.base import (
    DownloadResult, HostAdapter, ProbeResult, dl_wait_ms,
)
from scrape_all.downloader.fsutil import sanitize_filename

# hanime1.me：流媒体源站（SOURCE_HOSTS 里的 kind=source，此前只登记不下载）。
# 库内 84 条，形态 /watch?v=<id> 为主（少量 /download?v=），两者同一 id，统一走
# 站内 download 页（= watch 页 downloadBtn 的 href，直接构造省一跳）。
#
# 页面流（零 API、不点广告按钮）：
#   打开   https://hanime1.me/download?v=<id>，服务端渲染的 table.download-table
#         每档画质一行，行尾 <a data-url="CDN 直链（带短期 token）" download="真名">下載</a>
#   选档   画质文本里解析分辨率数字（(1080p)/(720p)/(480p)），取最大；解析不出保页面原序
#         （页面按高清->标清排列，首行兜底即最高）
#   下载   锚点没有 href（点击被站内 JS 接管），CDN 直链多数是内联 video/mp4 无
#         attachment 头，跨域 download 属性又被 Chromium 忽略——原生导航只会
#         内联播放，永不出下载事件。等价复刻站内 JS 的真实下载：把本页先导航
#         到直链（落在 CDN origin 绕开 CORS，顺带从响应头拿 content-length），
#         页内同源 fetch 整文件 -> blob -> objectURL 锚点点出下载事件 -> save_as。
#         体积列是 N/A，等待按 content-length 放大（engine.blob_download 同款思路，
#         但那个原语内部抢信号量，slot() 里调会死锁，故页内自实现）。
#         个别直链（无编号 vdownload 主机）带 Content-Disposition: attachment：
#         goto 当场触发下载被浏览器取消（"Download is starting"），页面没离开
#         站内 origin、页内 fetch 跨域必挂——这条岔路收下载事件直接 save_as
#   幂等   真名（download 属性 + 扩展名）先算好，已存在就不发起导航（0 流量）；
#         同系列不同视频可能同名（站点就给一样的 download 属性），同夹撞名时
#         以 {stem}.{vid}{ext} 区分出第二把，连后缀名都存在才算真重复
#
# 状态判定：跳登录页 -> needs_auth；http 404/410 -> dead；表格渲染不出 -> unknown
# （死链页真实形态未标定，先保守不判死，真页验证后再收紧）。
#
# 注意：stealth 会话（patchright）抛的 TimeoutError 与 playwright 的不同类，
# 事件等待的超时要按消息特征兜底接（引擎无关），见 download()。

_ROOT = "https://hanime1.me"
_TABLE_WAIT_MS = 15000
_SETTLE_MS = 1200
_EVENT_BASE_S = 60.0      # 事件要等页内 fetch 拉完整个 blob，按体积放大（见上）

_RESOLUTION_RE = re.compile(r"(\d{3,4})\s*p", re.I)
# 与 topic_parse.VIDEO_EXTS 同集合（那里在 sites 包，downloader 不反向依赖）
_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".wmv", ".mov", ".webm", ".m4v"}

# download 页表格 -> [{i, url, name, quality, ext}]（i 保页面原序，选档 tie-break 用）
_TABLE_ROWS_JS = """() => Array.from(document.querySelectorAll(
    'table.download-table tr')).map((tr, i) => {
  const a = tr.querySelector('a[data-url]');
  if (!a) return null;
  const tds = tr.querySelectorAll('td');
  return {i,
          url: a.dataset.url || '',
          name: a.getAttribute('download') || '',
          quality: tds.length > 1 ? tds[1].innerText.trim() : '',
          ext: tds.length > 2 ? tds[2].innerText.trim() : ''};
}).filter(Boolean)"""

# 页内同源 fetch -> blob -> objectURL 锚点保存（blob: 同源，download 属性生效，
# 无需用户手势）。出错返回错误串，成功返回 ""。与 engine.blob_download 同款，
# 但不抢引擎信号量（adapter 已在 slot() 里）
_FETCH_BLOB_JS = """async ({url, name}) => {
  try {
    const resp = await fetch(url, {credentials: "include"});
    if (!resp.ok) return "HTTP " + resp.status;
    const blob = await resp.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    return "";
  } catch (e) { return String(e); }
}"""


def parse_hanime_url(url: str) -> str | None:
  """/watch?v= 或 /download?v= -> 视频 id；search 等非视频形态返回 None"""
  parts = urlsplit(url)
  if parts.path not in ("/watch", "/download"):
    return None
  vid = (parse_qs(parts.query).get("v") or [""])[0]
  return vid or None


def row_resolution(quality: str) -> int:
  """画质文本里的分辨率数字（'全高清畫質 (1080p)' -> 1080）；认不出 -1"""
  m = _RESOLUTION_RE.search(quality or "")
  return int(m.group(1)) if m else -1


def pick_best_row(rows: list[dict]) -> dict | None:
  """最高画质行：分辨率降序，同分/都认不出时保页面原序（首行在前）"""
  if not rows:
    return None
  return max(enumerate(rows),
             key=lambda kv: (row_resolution(kv[1].get("quality", "")), -kv[0]))[1]


def local_filename(row: dict, vid: str) -> str:
  """落盘名：download 属性真名（通常无扩展名）+ 扩展名（CDN 路径优先，表格
  类型列兜底）。真名自带视频扩展名时不追加（避免 clip.mp4 变 clip.mp4.mkv）"""
  name = (row.get("name") or "").strip()
  path_ext = os.path.splitext(urlsplit(row.get("url") or "").path)[1].lower()
  ext = path_ext
  if not ext:
    col = (row.get("ext") or "").strip().lstrip(".")
    ext = f".{col.lower()}" if col else ""
  if not name:
    name = f"hanime_{vid}_{row.get('quality') or 'video'}"
  has_video_ext = any(name.lower().endswith(e) for e in _VIDEO_EXTS)
  if ext and not has_video_ext and not name.lower().endswith(ext):
    name += ext
  return name


def resolve_dest(dest_dir: str, name: str, vid: str) -> tuple[str, bool]:
  """(落盘路径, 是否真重复)。站点会给同系列不同视频完全相同的 download 真名
  （同帖归档同夹即撞名），撞名时以 {stem}.{vid}{ext} 区分出第二把；连
  后缀名都已存在才算真重复（0 流量 skipped）。"""
  dest = os.path.join(dest_dir, name)
  if not os.path.exists(dest):
    return dest, False
  stem, ext = os.path.splitext(name)
  alt = os.path.join(dest_dir, f"{stem}.{vid}{ext}")
  if not os.path.exists(alt):
    return alt, False
  return dest, True


def is_download_nav_error(exc: Exception) -> bool:
  """goto 撞 attachment 直链时，playwright/patchright 都会取消导航并抛
  'Download is starting'（下载已在路上，收事件即可）。按消息特征认，引擎无关。"""
  return "Download is starting" in str(exc)


class HanimeAdapter(HostAdapter):
  hosts = frozenset({"hanime1.me"})

  async def _open_download_page(self, engine, vid: str):
    """开 download 页等表格渲染。返回 (page, http_status)；调用方负责 close。
    表格等不到不在这判——页面形态（登录墙/挑战页/死链）留给调用方分类。"""
    page = await engine.context.new_page()
    resp = await page.goto(f"{_ROOT}/download?v={vid}",
                           wait_until="domcontentloaded", timeout=30000)
    try:
      await page.wait_for_selector("table.download-table a[data-url]",
                                   timeout=_TABLE_WAIT_MS)
    except PWTimeoutError:
      pass
    await page.wait_for_timeout(_SETTLE_MS)
    return page, (resp.status if resp else None)

  async def _rows(self, page) -> list[dict]:
    try:
      return await page.evaluate(_TABLE_ROWS_JS)
    except Exception:
      return []

  async def probe(self, engine, url: str) -> ProbeResult:
    vid = parse_hanime_url(url)
    if not vid:
      return ProbeResult("unknown", note=f"非视频页形态: {url}")
    async with engine.slot():
      try:
        page, status = await self._open_download_page(engine, vid)
      except Exception as e:
        return ProbeResult("unknown", note=str(e))
      try:
        if "login" in page.url:
          return ProbeResult("needs_auth", note="跳登录页，需人工登录一次")
        rows = await self._rows(page)
        if not rows:
          if status in (404, 410):
            return ProbeResult("dead", note=f"http {status}")
          title = await page.title()
          return ProbeResult("unknown",
                             note=f"无画质表格 http {status or '?'} title={title[:40]}")
        best = pick_best_row(rows)
        quals = "/".join(r.get("quality", "?") for r in rows)
        return ProbeResult("alive", filename=local_filename(best, vid),
                           note=f"{vid} {len(rows)} 档[{quals}] 取最高")
      finally:
        await page.close()

  async def download(self, engine, url: str, dest_dir: str) -> DownloadResult:
    vid = parse_hanime_url(url)
    if not vid:
      return DownloadResult("failed", note=f"非视频页形态: {url}")
    async with engine.slot():
      try:
        page, status = await self._open_download_page(engine, vid)
      except Exception as e:
        return DownloadResult("failed", note=str(e))
      try:
        if "login" in page.url:
          return DownloadResult("manual", note="跳登录页，需人工登录一次")
        rows = await self._rows(page)
        if not rows:
          if status in (404, 410):
            return DownloadResult("dead", note=f"http {status}")
          title = await page.title()
          return DownloadResult(
              "failed", note=f"无画质表格 http {status or '?'} title={title[:40]}")
        best = pick_best_row(rows)
        data_url = (best.get("url") or "").strip()
        if not data_url.startswith("http"):
          return DownloadResult("failed", note=f"data-url 缺失: {best!r}")

        # 幂等：真名先算好；同名撞车（同系列不同视频同名）以 vid 后缀区分，
        # 只有 vid 后缀名也已存在才 0 流量 skipped
        name = local_filename(best, vid)
        dest, exists = resolve_dest(dest_dir, sanitize_filename(name), vid)
        if exists:
          return DownloadResult("skipped", path=dest, note="已存在")

        os.makedirs(dest_dir, exist_ok=True)
        # 先把本页导航到直链：落在 CDN origin（后续 fetch 同源不受 CORS 限），
        # 顺带从响应头拿 content-length 供等待放大。导航失败不挡——照样试 fetch
        size = None
        downloads: list = []
        # 注意不能把 list.append 这种内建方法直接给 on()——事件包装器要摸
        # 回调对象属性，内建方法没有，当场 AttributeError
        page.on("download", lambda d: downloads.append(d))
        try:
          resp = await page.goto(data_url, timeout=30000)
          clen = (resp.headers.get("content-length")
                  if resp is not None else None)
          if clen and clen.isdigit():
            size = int(clen)
        except Exception as e:
          if is_download_nav_error(e):
            # attachment 直链：goto 被取消但浏览器已在下载。事件派发与 goto
            # 抛错有竞态，短轮询等监听器接住再收件
            dl = None
            for _ in range(20):
              if downloads:
                dl = downloads[-1]
                break
              await page.wait_for_timeout(100)
            if dl is not None:
              try:
                await dl.save_as(dest)
                return DownloadResult(
                    "downloaded", path=dest, size=os.path.getsize(dest),
                    note=f"{best.get('quality') or ''} attachment 直链".strip())
              except Exception as se:
                return DownloadResult(
                    "failed", note=f"attachment 直链收件失败 {se}")
          # 其他导航失败不挡——照样试 fetch
        # 页内 fetch 整文件 -> blob -> objectURL 锚点 -> 下载事件（事件在 blob
        # 拉完后才点出，等待按体积放大）；patchright 的 TimeoutError 与
        # playwright 的不同类，按消息特征兜底接成 failed
        try:
          async with page.expect_download(
              timeout=dl_wait_ms(size, _EVENT_BASE_S)) as dl_info:
            err = await page.evaluate(_FETCH_BLOB_JS,
                                      {"url": data_url, "name": name})
          if err:
            return DownloadResult("failed", note=f"页内 fetch 失败 {err}")
          download = await dl_info.value
        except Exception as e:
          if isinstance(e, PWTimeoutError) or "waiting for event" in str(e):
            return DownloadResult(
                "failed", note=f"无下载事件 size={size or '?'} "
                               f"{best.get('quality') or ''}".strip())
          raise
        await download.save_as(dest)
        return DownloadResult("downloaded", path=dest, size=os.path.getsize(dest),
                              note=f"{best.get('quality') or ''} {size or '?'}B".strip())
      finally:
        await page.close()
