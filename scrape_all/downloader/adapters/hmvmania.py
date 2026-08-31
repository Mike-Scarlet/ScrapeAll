
import os
import re
from urllib.parse import urlsplit

from scrape_all.downloader.adapters.base import (
    DownloadResult, HostAdapter, ProbeResult, is_wait_timeout, size_from_range_headers,
)
from scrape_all.downloader.fsutil import sanitize_filename, url_token

# hmvmania.com：流媒体源站第三家（WordPress + viewtube 主题）。页面流里最简的一家
# （零 API、零 token、零跨域）：
#   打开   视频页服务端渲染 ul.video-meta 元信息列表，下载项是
#         <li><i class="fas fa-download"></i><a href="…/wp-content/uploads/…mp4"
#         download>DL</a></li>——锚点静态渲染（curl 裸拉就有），与播放器无耦合；
#         选择器 a[download][href^='http'] 框在 ul.video-meta 里：播放器 JS
#         模板另有条 <a href="{{ data.url }}" download>Download file</a>，
#         href 属性非 http 前缀被排除——rows JS 与点击 nth 用同一属性值语义，
#         索引严格对齐
#   选档   一视频一文件（12 页抽查全单档），真名前缀即规格：av1_1080p_/
#         av1_720p_（AV1 编码+分辨率），个别无标记（Zen-AGEPLAY.mp4）。锚文本
#         恒为 "DL" 没信息量，分辨率从 href basename 解析；保险起见按多档写，
#         取最高且 <= 1080p 上限（与 rule34 同策省流量），认不出保页面原序
#   下载   href 是同源 wp-content 静态直链 + download 属性——点击即下载事件
#         （无 attachment 头也强制落盘），浏览器下载器流式落盘
#   体积   文件就在 hmvmania.com origin（CF 边缘缓存），视频页内直接同源
#         Range:0-0 fetch 读 content-range 总长——不用 rule34 的最终 origin
#         停页把戏；probe 全程 0 正文流量 0 点击
#   会话   无 token 无 referer 墙（curl 裸探 206），href 跨会话稳定，普通会话
#         即可（stealth 不必须，吃 CF 挑战时再加）
#
# 状态判定：http 404/410 -> dead；标题命中 CF 特征 -> unknown（挑战页，等人工）；
# 其余渲染不出 -> unknown（probe）/ failed（download）。会员墙形态未标定（页面
# 登录字样均为导航装饰，12 页抽查无缺失 DL 的形态），先保守不判 needs_auth，
# 真页验证后再收紧。非 /video/<slug>/ 形态（/author/ 页、wp-content 直链、
# 分类页）不是视频页，parse 返回 None 直接挡。

_SEL = "ul.video-meta a[download][href^='http']"
_MAX_RES = 1080
_GOTO_MS = 45000
_SEL_WAIT_MS = 20000
_SETTLE_MS = 1200
_EVENT_WAIT_MS = 60000        # 点击 -> 事件是即时的，不按体积放大（save_as 不限时）
_RANGE_TIMEOUT_MS = 30000

_VIDEO_PATH_RE = re.compile(r"^/video/([^/]+)/?$")
_RES_RE = re.compile(r"(\d{3,4})\s*p", re.I)
_CHALLENGE_MARKS = ("Just a moment", "Attention Required",
                    "Verify you are human", "Enable JavaScript")

_ROWS_JS = """() => Array.from(
    document.querySelectorAll("ul.video-meta a[download][href^='http']"))
  .map((a, i) => ({i, text: (a.innerText || '').trim(),
                   href: a.getAttribute('href') || ''}))"""

# 视频页内的同源 Range:0-0：读完响应头立刻 abort，0 正文流量
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


def parse_hmvmania_url(url: str) -> str | None:
  """/video/<slug>/ -> slug（该站无数字 id，slug 即身份，尾斜杠可有可无）；
  /author/、/video-category/、wp-content 直链等非视频形态返回 None"""
  m = _VIDEO_PATH_RE.match(urlsplit(url).path)
  return m.group(1) if m else None


def row_resolution(href: str) -> int:
  """直链 basename 里的分辨率数字（'av1_1080p_xxx.mp4' -> 1080；锚文本恒为
  'DL' 没信息量，只认 href）；认不出 -1"""
  base = os.path.basename(urlsplit(href or "").path)
  m = _RES_RE.search(base)
  return int(m.group(1)) if m else -1


def pick_best_row(rows: list[dict], max_res: int = _MAX_RES) -> dict | None:
  """最高分辨率且 <= max_res 的档；同分保页面原序；全部超上限/认不出取首行
  兜底（上限是选档偏好不是硬墙，档位信息留在 note 里给编排层判）"""
  if not rows:
    return None
  ok = [(i, r) for i, r in enumerate(rows)
        if 0 < row_resolution(r.get("href", "")) <= max_res]
  if ok:
    return max(ok, key=lambda kv: (row_resolution(kv[1]["href"]), -kv[0]))[1]
  return rows[0]


def local_filename(row: dict, slug: str) -> str:
  """落盘名：直链 basename（站点自命名 av1_1080p_真名.mp4，跨会话稳定）；
  缺档时 hmvmania_{slug}"""
  name = os.path.basename(urlsplit(row.get("href") or "").path).strip()
  if name:
    return name
  return f"hmvmania_{slug}.mp4"


class HmvmaniaAdapter(HostAdapter):
  hosts = frozenset({"hmvmania.com"})

  async def _open_video_page(self, engine, url: str):
    """开视频页等下载锚点渲染。锚点是静态 HTML（curl 裸拉就有），等选择器只是
    兜底。返回 (page, http_status)；调用方负责 close。"""
    page = await engine.context.new_page()
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=_GOTO_MS)
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

  async def _file_size(self, page, url: str) -> tuple[int | None, str]:
    """(字节, note)：视频页内同源 Range:0-0 读总长（文件与页面同 origin）。
    任何失败返回 (None, note)，不挡主流程。"""
    try:
      out = await page.evaluate(_RANGE_JS,
                                {"url": url, "timeoutMs": _RANGE_TIMEOUT_MS})
    except Exception as e:
      return None, f"探体积失败 {str(e)[:50]}"
    status = out.get("status")
    if status not in (200, 206):
      return None, f"直链 http {status}"
    return size_from_range_headers(out.get("headers", {})), f"range {status}"

  def _best_note(self, best: dict, rows: list[dict]) -> str:
    quals = "/".join(
        os.path.basename(urlsplit(r.get("href", "")).path) or "?"
        for r in rows)
    picked = os.path.basename(urlsplit(best.get("href", "")).path) or "?"
    note = f"{len(rows)} 档[{quals[:120]}] 取 {picked}"
    if row_resolution(best.get("href", "")) > _MAX_RES:
      note += f"（超{_MAX_RES}p上限兜底首档）"
    return note

  async def probe(self, engine, url: str) -> ProbeResult:
    slug = parse_hmvmania_url(url)
    if not slug:
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
          title = await page.title()
          return ProbeResult(
              "unknown", note=f"无下载锚点 http {status or '?'} title={title[:40]}")
        best = pick_best_row(rows)
        href = best.get("href") or ""
        # 直链同源静态文件，Range 206 即链路真章（0 正文流量 0 点击）；
        # 失败不翻 dead，只进 note（rule34 同策）
        size, extra = await self._file_size(page, href)
        return ProbeResult("alive", filename=sanitize_filename(
            local_filename(best, slug)), size=size,
            note=f"{slug} {self._best_note(best, rows)} {extra}".strip())
      finally:
        await page.close()

  async def download(self, engine, url: str, dest_dir: str) -> DownloadResult:
    slug = parse_hmvmania_url(url)
    if not slug:
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
          return DownloadResult("failed", note=f"无下载锚点 http {status or '?'}")
        best = pick_best_row(rows)
        if not (best.get("href") or "").startswith("http"):
          return DownloadResult("failed", note=f"href 缺失: {best!r}")

        # 幂等：直链 basename 跨会话稳定（无 token），已存在就不点（0 流量）；
        # 并发撞名由引擎落 {stem}.{token}{ext} 第二把
        name = sanitize_filename(local_filename(best, slug))
        dest = os.path.join(dest_dir, name)
        if os.path.exists(dest):
          return DownloadResult("skipped", path=dest,
                                size=os.path.getsize(dest), note="已存在")

        os.makedirs(dest_dir, exist_ok=True)
        try:
          async with page.expect_download(timeout=_EVENT_WAIT_MS) as dl_info:
            await page.locator(_SEL).nth(best["i"]).click()
          download = await dl_info.value
        except Exception as e:
          if is_wait_timeout(e):
            return DownloadResult("failed", note="点击后无下载事件")
          raise
        # 落盘走引擎收口（save_as 不限时，浏览器下载器流式写盘）
        dest = await engine.save_download(download, dest_dir, name, url_token(url))
        return DownloadResult("downloaded", path=dest, size=os.path.getsize(dest),
                              note=f"{best.get('text') or 'DL'}".strip())
      finally:
        await page.close()
