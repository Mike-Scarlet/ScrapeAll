
import os
import re
from urllib.parse import urlsplit

from playwright.async_api import TimeoutError as PWTimeoutError

from scrape_all.downloader.adapters.base import (
    DownloadResult, HostAdapter, ProbeResult, dl_wait_ms,
)
from scrape_all.downloader.fsutil import sanitize_filename

# pixeldrain：eroscripts 媒体链接主力（EroLink 现存 190 条：/d 77、/l 72、/u 41）。
#
# 全页面流，零 API 调用（真人模式：开页面 -> 读渲染结果 -> 点页面按钮）：
#   探活   死链页面 title 是 "404, File|List Not Found ~ pixeldrain"（或 goto
#         直接 404）；活文件页 title 即文件名、.stat 父块按 "Size" 标签读体积
#   下载   /u 文件页点 button.toolbar_button（文本 Download）；列表页点
#         button[title*="zip archive"]（DL all files，整包 zip）；/d 页见下
#   幂等   落盘名先算好，已存在就不点按钮——不产生任何下载流量
#
# 历史教训（别再踩）：/api/file/{id} 是文件本体不是元信息 JSON，首版拿
# resp.json() 去读 1.8GB 的 7z body 才出现"API 挂死"假象；API 也可用（列表
# JSON / Range 探头都验证过），但按约定走页面按钮。
#
# 形态透传（2026-08 修复）：站点侧 /u 与 /d 页面逐文件互斥（实测 E1Kk51Ls
# 只有 /d 页、PV82t9fy 只有 /u 页，另一形态 404），帖子里的原始形态是唯一
# 可靠入口——首版把形态折叠成一律开 /u，库内 77 条 /d 链接全军误判 dead。
# 现在 parse_pd_url 保留 form，file 且 form=d 直接开 /d 页；api 形态没有页面
# 语义，仍落 /u /l 规范页。/d 页（另一套 UI）两处差异：动作栏按钮无
# toolbar_button 类（同样按文本 Download 筛选，实测第一颗 save/Download 触发
# 下载事件）；.stat 父块混着 "Transfer used" 带宽，体积必须按 "Size" 标签锚定
# （取最大值会把 129MB 的文件报成 185GB）。

_PD_ROOT = "https://pixeldrain.com"
_TITLE_SUFFIX = " ~ pixeldrain"
_SIZE_TEXT_RE = re.compile(r"([\d.]+)\s*(B|KB|MB|GB|TB)", re.I)
# .stat 父块文本里的体积标签（"Size\n129 MB"）；锚不到的不算数
_SIZE_LABEL_RE = re.compile(r"size\s*([\d.]+\s*(?:B|KB|MB|GB|TB))", re.I)
# pixeldrain 的 .stat 是 1000 进制显示（实测对拍：14.0 MB = 14020206 字节、
# 51.1 MB = 51092113 字节），按 SI 单位换算
_SIZE_MULT = {"B": 1, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3, "TB": 1000 ** 4}

_TOOLBAR_BTN = "button.toolbar_button"          # /u 文件页 Download 按钮
_LIST_DL_BTN = 'button[title*="zip archive"]'   # 列表页 DL all files 按钮
_SETTLE_MS = 1200        # domcontentloaded 后给 svelte 渲染的时间
_CLICK_WAIT_MS = 15000   # 等按钮出现


def parse_pd_url(url: str) -> tuple[str, str, str] | None:
  """pixeldrain URL -> ("file"|"list", id, form)；认不出的形态返回 None。
  form 保留原始形态（u/d/api_file/l/api_list）——/u 与 /d 页面逐文件互斥，
  帖子里的形态是唯一可靠入口，不能在解析边界折叠掉"""
  path = urlsplit(url).path
  m = re.match(r"^/(u|d|api/file)/([A-Za-z0-9]+)", path)
  if m:
    return "file", m.group(2), m.group(1).replace("/", "_")
  m = re.match(r"^/(l|api/list)/([A-Za-z0-9]+)", path)
  if m:
    return "list", m.group(2), m.group(1).replace("/", "_")
  return None


def pd_page_url(kind: str, pid: str, form: str) -> str:
  """(kind, id, form) -> 要开的页面地址。file 且原形态是 d 就开 /d（开 /u
  会 404）；其余落规范页——u/l 本来就是页面形态，api 形态没有页面语义"""
  if kind == "file" and form == "d":
    return f"{_PD_ROOT}/d/{pid}"
  return f"{_PD_ROOT}/{'l' if kind == 'list' else 'u'}/{pid}"


def name_from_title(title: str) -> str:
  """页面 title 去掉站点后缀 -> 文件名/列表名"""
  if title.endswith(_TITLE_SUFFIX):
    return title[: -len(_TITLE_SUFFIX)]
  return title


def parse_size_text(text: str) -> int | None:
  """页面上的人读体积（"14.0 MB"）-> 近似字节；认不出返回 None"""
  m = _SIZE_TEXT_RE.search(text or "")
  if not m:
    return None
  try:
    return int(float(m.group(1)) * _SIZE_MULT[m.group(2).upper()])
  except ValueError:
    return None


def _is_dead(title: str, status: int | None) -> bool:
  if status in (404, 410):
    return True
  return bool(title) and title.startswith("404")


async def labeled_file_size(page) -> int | None:
  """文件页体积：锚 .stat 父块里的 "Size <值>"。/d 页 .stat 各自带标签父块
  （混着 "Transfer used" 带宽），/u 页三个 .stat 共享一个标签父块，两种
  结构这个读法都锚得到；锚不到返回 None（等待超时退回地板值）"""
  blocks = await page.locator(".stat").evaluate_all(
      "els => els.map(e => e.parentElement.innerText)")
  for text in blocks:
    m = _SIZE_LABEL_RE.search(text or "")
    if m:
      return parse_size_text(m.group(1))
  return None


async def _stat_sizes(page) -> list[int]:
  """页面 .stat 元素里能解析成体积的文本（近似值）"""
  texts = await page.locator(".stat").all_inner_texts()
  sizes = [s for s in (parse_size_text(t) for t in texts) if s]
  return sizes


def est_size_from_stats(sizes: list[int]) -> int | None:
  """列表页 .stat 是逐文件体积，求和≈整包 zip 大小。读不到返回 None
  （等待超时退回地板值）"""
  return sum(sizes) if sizes else None


class PixeldrainAdapter(HostAdapter):
  hosts = frozenset({"pixeldrain.com"})

  async def _open_page(self, engine, url: str):
    """开页面并等渲染，返回 (page, http_status)。调用方负责 close"""
    page = await engine.context.new_page()
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(_SETTLE_MS)
    return page, (resp.status if resp else None)

  async def probe(self, engine, url: str) -> ProbeResult:
    parsed = parse_pd_url(url)
    if not parsed:
      return ProbeResult("unknown", note=f"无法解析的 pixeldrain 形态: {url}")
    kind, pid, form = parsed

    async with engine.slot():
      try:
        page, status = await self._open_page(engine, pd_page_url(kind, pid, form))
      except Exception as e:
        return ProbeResult("unknown", note=str(e))
      try:
        title = await page.title()
        if _is_dead(title, status):
          return ProbeResult("dead", note=f"http {status or '?'} {title[:40]}")
        name = name_from_title(title)
        if kind == "file":
          size = await labeled_file_size(page)
          extra = ("（/d 形态）" if form == "d" else "") + \
                  ("（体积为页面近似值）" if size else "")
          return ProbeResult("alive", filename=name, size=size,
                             note=f"file {pid}{extra}")
        return ProbeResult("alive", filename=name,
                           note=f"list {pid}（下载为整包 zip）")
      finally:
        await page.close()

  async def download(self, engine, url: str, dest_dir: str) -> DownloadResult:
    parsed = parse_pd_url(url)
    if not parsed:
      return DownloadResult("failed", note=f"无法解析的 pixeldrain 形态: {url}")
    kind, pid, form = parsed

    async with engine.slot():
      target = pd_page_url(kind, pid, form)
      try:
        page, status = await self._open_page(engine, target)
      except Exception as e:
        return DownloadResult("failed", note=str(e))
      try:
        title = await page.title()
        if _is_dead(title, status):
          return DownloadResult("dead", note=f"http {status or '?'} {title[:40]}")
        name = name_from_title(title)

        # 幂等：文件已在就别点按钮（0 流量）
        local_name = sanitize_filename(
            name if kind == "file" else f"{name}.zip")
        if os.path.exists(os.path.join(dest_dir, local_name)):
          return DownloadResult("skipped",
                                path=os.path.join(dest_dir, local_name),
                                note="已存在")

        if kind == "list":
          btn = page.locator(_LIST_DL_BTN).first
          est = est_size_from_stats(await _stat_sizes(page))
        elif form == "d":
          # /d 页动作栏没有 toolbar_button 类，按文本筛第一颗 Download 按钮
          # （实测 save/Download，事件 suggested 名就是真文件名）
          btn = page.locator("button").filter(
              has_text=re.compile(r"download", re.I)).first
          est = await labeled_file_size(page)
        else:
          btn = page.locator(_TOOLBAR_BTN).filter(
              has_text=re.compile(r"download", re.I)).first
          est = await labeled_file_size(page)
        try:
          await btn.wait_for(state="visible", timeout=_CLICK_WAIT_MS)
        except PWTimeoutError:
          return DownloadResult("failed", note=f"下载按钮未渲染: {target}")

        os.makedirs(dest_dir, exist_ok=True)
        # 列表 ZIP 是服务端现打包（事件要等打包开始才来），等待按体积放
        async with page.expect_download(timeout=dl_wait_ms(est, 60)) as dl_info:
          await btn.click()
        download = await dl_info.value
        dest = os.path.join(
            dest_dir,
            sanitize_filename(download.suggested_filename or local_name))
        await download.save_as(dest)
        return DownloadResult("downloaded", path=dest, size=os.path.getsize(dest))
      finally:
        await page.close()
