
import asyncio
import os
import re
from urllib.parse import urlsplit

from playwright.async_api import TimeoutError as PWTimeoutError

from scrape_all.downloader.adapters.base import (
    DownloadResult, HostAdapter, ProbeResult, dl_wait_ms,
)
from scrape_all.downloader.fsutil import sanitize_filename

# mega.nz：库内 208 条（131 folder + 68 file 形态，密钥都在 URL hash）。全页面流。
#
# 实测页面行为（2026-08-24，真紅/isami_ride 多轮联调 + 人工指认确认）：
#   死链     http 200 且 title 正常演化（'Download - MEGA'）不可信；判定靠正文
#            三种死文案：无法访问该文件 / 该文件夹不再可用 / 此内容已被移除
#   file 页  .dl-header .fileinfo 里 .name 与 .ext 分开放，.size 是 "144.8 mb"
#            （nbsp 分隔、单位大小写混杂）；下载按钮是 header 图标按钮
#            button[data-simpletip="下载"]（人工确认即日常所用）
#   folder 页 行 = a.mega-node.fm-item（注意是 <a> 不是 tr）；体积+名在 title
#            属性（"15 KB 名字"；mp4 行还带 "1280x1080 @30fps isom/avc1" 前缀，
#            体积解析必须词边界锚定）；.size span 在卡片视图为空不可用
#   下载     全部在页面内完成：分块拉 userstorage.mega.co.nz -> 内存解密 ->
#            （folder 再打包 zip）-> 浏览器下载事件。事件出现时间 ≈ 体积/网速
#            （实测 39.5MB=14s），cancel 前流量已花完，等待超时给足 5 分钟
#   folder   刻意不选中任何行：button.fm-download -> 菜单「下载为ZIP」->
#            整夹打包，suggested = 文件夹真名.zip（完全绕开选中态语义——
#            选中态实测有"点了 A 下成 B"的未解之谜，不依赖它）
#   弹窗     偶发「连接桌面应用程序」sheet，点『好的，明白了』关掉（看门狗）
#
# zh 依赖：死文案 / data-simpletip="下载" / 好的，明白了 均为中文 locale 字符串，
# browser_session profile 固定 zh-CN，换语言需同步改这里。

_DEAD_MARKS = ("无法访问该文件", "该文件夹不再可用", "此内容已被移除")
_ROW_SEL = "a.mega-node.fm-item"
# 公开夹有两种视图 DOM（2026-08 实测）：常规夹走 a.mega-node 行；根目录全是
# 子文件夹的夹走网格表格 table.grid-table -> tr.megaListItem，前者选择器在
# 后者页面一个都匹配不到——ready 判据两个都得认，否则 probe 误报 unknown
_GRID_ROW_SEL = "table.grid-table tbody tr.megaListItem"
_FOLDER_READY_SEL = f"{_ROW_SEL}, {_GRID_ROW_SEL}"
_FILE_NAME_SEL = ".dl-header .fileinfo .filename .name"
_FILE_EXT_SEL = ".dl-header .fileinfo .filename .ext"
_FILE_SIZE_SEL = ".dl-header .fileinfo .size"
_FILE_DL_BTN = ".dl-header button[data-simpletip='下载']"
_ZIP_MENU_BTN = ".fm-download-menu button:has(.icon-download-zip)"
_OK_BTN = "button:has-text('好的，明白了')"
_SIZE_TEXT_RE = re.compile(r"(?:^|\s)([\d.]+)\s*(B|KB|MB|GB|TB)(?:\s|$)", re.I)
_SIZE_MULT = {"B": 1, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3, "TB": 1000 ** 4}
_WAIT_MS = 40000           # SPA 判定 + 渲染上限（实测 10s 内出结果；并发抢代理
                           # 带宽时 folder 页更慢，20s 两连挂过，放宽到 40s）
_POLL_MS = 500
_DL_WAIT_MS = 300000       # 下载事件等待地板：页面内整文件拉完才出事件，
                           # 体积读得到时按 200KB/s 兜底网速放宽（见 base）


def parse_mega_url(url: str) -> tuple[str, str] | None:
  """mega URL -> ("file"|"folder", 节点id)；/folder/{id}/{子节点} 归 folder；
  认不出的形态返回 None（host 校验归 matches()）"""
  segs = [s for s in urlsplit(url).path.split("/") if s]
  if len(segs) >= 2 and segs[0] in ("file", "folder") and segs[1]:
    return segs[0], segs[1]
  return None


def parse_size_text(text: str) -> int | None:
  """title/size 文本里的人读体积（十进制显示）-> 近似字节。
  词边界锚定：mp4 行 title 带 "1280x1080 @30fps" 前缀，不锚会误读成 1080"""
  m = _SIZE_TEXT_RE.search(text or "")
  if not m:
    return None
  try:
    return round(float(m.group(1)) * _SIZE_MULT[m.group(2).upper()])
  except ValueError:
    return None


def grid_row(g: dict) -> dict | None:
  """网格视图行（page.evaluate 原始结构）-> {id, name, size, is_dir}。
  名字=第一个无类名且有文本的 td（实测名字列不带类）；体积/类型按 td 首类名
  定位；is_dir 认 tr 类里的 folder token（td.type 文案「文件夹」兜底）。"""
  def by_class(key: str) -> str:
    return next((t["txt"] for t in g["tds"]
                 if (t["cls"] or "").split()[:1] == [key]), "")
  name = next((t["txt"] for t in g["tds"] if not t["cls"] and t["txt"]), "")
  if not name:
    return None
  return {"id": g["id"], "name": name,
          "size": parse_size_text(by_class("size")),
          "is_dir": "folder" in (g["cls"] or "").split()
                    or by_class("type") == "文件夹"}


def zip_est_size(rows: list[dict]) -> int | None:
  """整夹 ZIP 等待窗口的体积估算：直下文件体积和优先；根目录全是子目录的
  夹（网格视图，直下 0 文件）用子目录体积和兜底——不兜的话 24GB 的 ZIP 会
  走 300s 地板被活活掐死。都读不到体积返回 None（调用方走地板）。"""
  files = sum(r["size"] or 0 for r in rows if not r["is_dir"])
  if files:
    return files
  return sum(r["size"] or 0 for r in rows) or None


async def _read_rows(page) -> list[dict]:
  """读 folder 文件行：[{id, name, size, is_dir}]；空行/占位行跳过。
  先按常规视图读，一个没有再按网格视图读（两种 DOM 见 _GRID_ROW_SEL 注释）"""
  rows = await page.evaluate(
      """() => [...document.querySelectorAll('a.mega-node.fm-item')]
           .filter(a => a.id && a.getAttribute('title'))
           .map(a => ({id: a.id, dir: a.classList.contains('folder'),
                       name: (a.querySelector('.fm-item-name')||{}).textContent || '',
                       title: a.getAttribute('title')}))""")
  out = []
  for r in rows:
    name = (r.get("name") or "").strip()
    if not name:
      continue
    out.append({"id": r["id"], "name": name,
                "size": parse_size_text(r.get("title")),
                "is_dir": bool(r.get("dir"))})
  if out:
    return out
  grid = await page.evaluate(
      """() => [...document.querySelectorAll('tr.megaListItem')]
           .filter(tr => tr.id)
           .map(tr => ({id: tr.id, cls: tr.className,
                       tds: [...tr.children].map(td => (
                           {cls: td.className,
                            txt: (td.innerText || '').trim()}))}))""")
  return [r for r in (grid_row(g) for g in grid) if r]


async def _sheet_watchdog(page):
  """下载等待期间偶发的『连接桌面应用程序』sheet：见『好的，明白了』就点掉"""
  while True:
    try:
      btn = page.locator(_OK_BTN)
      if await btn.count() and await btn.first.is_visible():
        await btn.first.click()
    except Exception:
      pass
    await asyncio.sleep(1.5)


async def _maybe_nag(page):
  """file 页/菜单点击后可能弹『用桌面 app 下载』劝导框，见『继续使用浏览器』就点"""
  try:
    nag = page.locator("button.continue-with-browser")
    await nag.wait_for(state="visible", timeout=4000)
    await nag.click()
  except PWTimeoutError:
    pass


class MegaAdapter(HostAdapter):
  hosts = frozenset({"mega.nz", "mega.link"})

  async def _open(self, engine, url: str):
    """开页并等 SPA 出结果。
    返回 ("dead"|"ready"|"needs_auth"|"unknown", page, note)；page 非 None 时
    由调用方 close。"""
    page = await engine.context.new_page()
    try:
      await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
      await page.close()
      return "unknown", None, f"goto 失败: {e}"
    kind = (parse_mega_url(url) or ("", ""))[0]
    ready_sel = _FOLDER_READY_SEL if kind == "folder" else _FILE_NAME_SEL
    deadline = asyncio.get_event_loop().time() + _WAIT_MS / 1000
    while asyncio.get_event_loop().time() < deadline:
      try:
        body = await page.locator("body").inner_text()
      except Exception:
        body = ""
      mark = next((m for m in _DEAD_MARKS if m in body), None)
      if mark:
        return "dead", page, mark
      try:
        if await page.locator(ready_sel).first.is_visible():
          return "ready", page, ""
        if await page.locator("input[type=password]").first.is_visible():
          return "needs_auth", page, "密码保护"
      except Exception:
        pass   # 页面跳转瞬间 locator 可能失效，下轮再查
      await page.wait_for_timeout(_POLL_MS)
    return "unknown", page, f"{_WAIT_MS}ms 内未渲染出结果"

  async def _read_file_header(self, page) -> tuple[str, int | None]:
    name = (await page.locator(_FILE_NAME_SEL).first.inner_text()).strip()
    ext = (await page.locator(_FILE_EXT_SEL).first.inner_text()).strip()
    size_txt = await page.locator(_FILE_SIZE_SEL).first.inner_text()
    return name + ext, parse_size_text(size_txt)

  async def probe(self, engine, url: str) -> ProbeResult:
    parsed = parse_mega_url(url)
    if not parsed:
      return ProbeResult("unknown", note=f"无法解析的 mega 形态: {url}")
    kind, nid = parsed
    async with engine.slot():
      state, page, note = await self._open(engine, url)
      if page is None:
        return ProbeResult("unknown", note=note)
      try:
        if state == "dead":
          return ProbeResult("dead", note=note)
        if state == "needs_auth":
          return ProbeResult("needs_auth", note=note)
        if state != "ready":
          return ProbeResult("unknown", note=note)
        if kind == "file":
          fname, size = await self._read_file_header(page)
          return ProbeResult(
              "alive", filename=fname, size=size,
              files=[{"name": fname, "size": size, "url": None}],
              note=f"{nid} 单文件（体积为页面近似值）")
        rows = await _read_rows(page)
        files = [r for r in rows if not r["is_dir"]]
        n_dir = len(rows) - len(files)
        total = sum(r["size"] or 0 for r in files)
        return ProbeResult(
            "alive",
            filename=files[0]["name"] if len(files) == 1 else f"folder:{nid}",
            size=files[0]["size"] if len(files) == 1 else (total or None),
            files=[{"name": r["name"], "size": r["size"], "url": None}
                   for r in files],
            note=(f"{nid} 直下 {len(files)} 文件"
                  + (f"、{n_dir} 子目录（本期不下）" if n_dir else "")
                  + (f"，共约 {total / 1e6:.0f}MB" if total else "")
                  + "（整夹走 ZIP 下载，体积为页面近似值）"))
      finally:
        await page.close()

  async def download(self, engine, url: str, dest_dir: str) -> DownloadResult:
    parsed = parse_mega_url(url)
    if not parsed:
      return DownloadResult("failed", note=f"无法解析的 mega 形态: {url}")
    kind, _ = parsed
    async with engine.slot():
      state, page, note = await self._open(engine, url)
      if page is None:
        return DownloadResult("failed", note=note)
      try:
        if state == "dead":
          return DownloadResult("dead", note=note)
        if state != "ready":
          return DownloadResult("failed", note=f"页面状态 {state}: {note}")
        os.makedirs(dest_dir, exist_ok=True)
        if kind == "file":
          return await self._download_file(page, dest_dir)
        return await self._download_folder_zip(page, dest_dir)
      finally:
        await page.close()

  async def _download_file(self, page, dest_dir: str) -> DownloadResult:
    fname, size = await self._read_file_header(page)
    local = sanitize_filename(fname)
    dest = os.path.join(dest_dir, local)
    if os.path.exists(dest):
      return DownloadResult("skipped", path=dest, note=f"{local} 已存在")
    wait_ms = dl_wait_ms(size, _DL_WAIT_MS / 1000)
    watchdog = asyncio.create_task(_sheet_watchdog(page))
    try:
      async with page.expect_download(timeout=wait_ms) as dl_info:
        await page.locator(_FILE_DL_BTN).first.click()
        await _maybe_nag(page)
      dl = await dl_info.value
      dest = os.path.join(
          dest_dir, sanitize_filename(dl.suggested_filename or local))
      await dl.save_as(dest)
      return DownloadResult(
          "downloaded", path=dest, size=os.path.getsize(dest),
          note=f"{os.path.basename(dest)}（页面内整文件拉取后落盘）")
    except PWTimeoutError as e:
      return DownloadResult(
          "failed", note=f"下载事件超时 {wait_ms // 1000}s: {e}")
    finally:
      watchdog.cancel()

  async def _download_folder_zip(self, page, dest_dir: str) -> DownloadResult:
    # ZIP 打包前读行体积：整夹拉完才出事件，等待按总体积放（>850MB 的夹子
    # 5 分钟地板根本兜不住；全是子目录的夹用地目录体积和，见 zip_est_size）
    est = zip_est_size(await _read_rows(page))
    wait_ms = dl_wait_ms(est, _DL_WAIT_MS / 1000)
    await page.locator("button.fm-download").click()
    await page.locator(".fm-download-menu").wait_for(state="visible", timeout=8000)
    watchdog = asyncio.create_task(_sheet_watchdog(page))
    try:
      async with page.expect_download(timeout=wait_ms) as dl_info:
        await page.locator(_ZIP_MENU_BTN).click()
        await _maybe_nag(page)
      dl = await dl_info.value
      suggested = dl.suggested_filename or "mega.zip"
      dest = os.path.join(dest_dir, sanitize_filename(suggested))
      # zip 名在事件出现才知道（= 文件夹真名.zip），幂等只能事后判：
      # 已存在就 cancel 不写盘（流量已在页面内花掉，属人工复跑场景）
      if os.path.exists(dest):
        await dl.cancel()
        return DownloadResult("skipped", path=dest,
                              note=f"{suggested} 已存在（复跑已拉取，未重复写盘）")
      await dl.save_as(dest)
      return DownloadResult(
          "downloaded", path=dest, size=os.path.getsize(dest),
          note=f"整夹 ZIP {suggested}（解压得原文件树）")
    except PWTimeoutError as e:
      return DownloadResult(
          "failed", note=f"ZIP 下载事件超时 {wait_ms // 1000}s: {e}")
    finally:
      watchdog.cancel()
