
import os
import re
from urllib.parse import urlsplit

from playwright.async_api import TimeoutError as PWTimeoutError

from scrape_all.downloader.adapters.base import (
    DownloadResult, HostAdapter, ProbeResult,
)
from scrape_all.downloader.fsutil import sanitize_filename

# pixeldrain：eroscripts 媒体链接主力（库内 ~895 条：/l 列表 431、/d 直链 259、
# /u 单文件页 205、裸 api 1）。
#
# 全页面流，零 API 调用（真人模式：开页面 -> 读渲染结果 -> 点页面按钮）：
#   探活   死链页面 title 是 "404, File|List Not Found ~ pixeldrain"（或 goto
#         直接 404）；活文件页 title 即文件名、.stat 文本给人读体积（"14.0 MB"）
#   下载   文件页点 button.toolbar_button（文本 Download）触发浏览器下载器；
#         列表页点 button[title*="zip archive"]（DL all files，整包 zip）
#   幂等   落盘名先算好，已存在就不点按钮——不产生任何下载流量
#
# 历史教训（别再踩）：/api/file/{id} 是文件本体不是元信息 JSON，首版拿
# resp.json() 去读 1.8GB 的 7z body 才出现"API 挂死"假象；API 也可用（列表
# JSON / Range 探头都验证过），但按约定走页面按钮。
# /u /d /l 只是同一 id 的不同形态，入口统一解析成 (file|list, id)，一律开
# /u/{id} 或 /l/{id} 页面操作。


_PD_ROOT = "https://pixeldrain.com"
_TITLE_SUFFIX = " ~ pixeldrain"
_SIZE_TEXT_RE = re.compile(r"([\d.]+)\s*(B|KB|MB|GB|TB)", re.I)
# pixeldrain 的 .stat 是 1000 进制显示（实测对拍：14.0 MB = 14020206 字节、
# 51.1 MB = 51092113 字节），按 SI 单位换算
_SIZE_MULT = {"B": 1, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3, "TB": 1000 ** 4}

_TOOLBAR_BTN = "button.toolbar_button"          # 文件页 Download 按钮
_LIST_DL_BTN = 'button[title*="zip archive"]'   # 列表页 DL all files 按钮
_SETTLE_MS = 1200        # domcontentloaded 后给 svelte 渲染的时间
_CLICK_WAIT_MS = 15000   # 等按钮出现


def parse_pd_url(url: str) -> tuple[str, str] | None:
  """pixeldrain URL -> ("file"|"list", id)；认不出的形态返回 None"""
  path = urlsplit(url).path
  m = re.match(r"^/(?:u|d|api/file)/([A-Za-z0-9]+)", path)
  if m:
    return "file", m.group(1)
  m = re.match(r"^/(?:l|api/list)/([A-Za-z0-9]+)", path)
  if m:
    return "list", m.group(1)
  return None


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


async def _stat_sizes(page) -> list[int]:
  """页面 .stat 元素里能解析成体积的文本（近似值）"""
  texts = await page.locator(".stat").all_inner_texts()
  sizes = [s for s in (parse_size_text(t) for t in texts) if s]
  return sizes


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
    kind, pid = parsed
    page_url = f"{_PD_ROOT}/{'l' if kind == 'list' else 'u'}/{pid}"

    async with engine.slot():
      try:
        page, status = await self._open_page(engine, page_url)
      except Exception as e:
        return ProbeResult("unknown", note=str(e))
      try:
        title = await page.title()
        if _is_dead(title, status):
          return ProbeResult("dead", note=f"http {status or '?'} {title[:40]}")
        name = name_from_title(title)
        if kind == "file":
          sizes = await _stat_sizes(page)
          # .stat 里最大的可解析体积是文件大小（views/downloads 是小整数，解析不出单位）
          size = max(sizes) if sizes else None
          return ProbeResult("alive", filename=name, size=size,
                             note=f"file {pid}" + ("（体积为页面近似值）" if size else ""))
        return ProbeResult("alive", filename=name,
                           note=f"list {pid}（下载为整包 zip）")
      finally:
        await page.close()

  async def download(self, engine, url: str, dest_dir: str) -> DownloadResult:
    parsed = parse_pd_url(url)
    if not parsed:
      return DownloadResult("failed", note=f"无法解析的 pixeldrain 形态: {url}")
    kind, pid = parsed

    async with engine.slot():
      page_url = f"{_PD_ROOT}/{'l' if kind == 'list' else 'u'}/{pid}"
      try:
        page, status = await self._open_page(engine, page_url)
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

        if kind == "file":
          btn = page.locator(_TOOLBAR_BTN).filter(
              has_text=re.compile(r"download", re.I)).first
        else:
          btn = page.locator(_LIST_DL_BTN).first
        try:
          await btn.wait_for(state="visible", timeout=_CLICK_WAIT_MS)
        except PWTimeoutError:
          return DownloadResult("failed", note=f"下载按钮未渲染: {page_url}")

        os.makedirs(dest_dir, exist_ok=True)
        async with page.expect_download(timeout=60000) as dl_info:
          await btn.click()
        download = await dl_info.value
        dest = os.path.join(
            dest_dir,
            sanitize_filename(download.suggested_filename or local_name))
        await download.save_as(dest)
        return DownloadResult("downloaded", path=dest, size=os.path.getsize(dest))
      finally:
        await page.close()
