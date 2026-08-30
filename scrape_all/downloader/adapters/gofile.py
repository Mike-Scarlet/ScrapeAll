
import asyncio
import os
import re
from urllib.parse import urlsplit

from playwright.async_api import TimeoutError as PWTimeoutError

from scrape_all.downloader.adapters.base import (
    DownloadResult, HostAdapter, ProbeResult, dl_wait_ms,
)
from scrape_all.downloader.fsutil import same_size_or_unknown, sanitize_filename, url_token

# gofile：库内 55 条，全部 /d/{id} 形态。全页面流（开页面 -> 读渲染 -> 点按钮）。
#
# 实测页面行为（2026-08-23，AuxExhX6 联调）：
#   死链     http 仍是 200！判定靠 SPA 渲染后的 title「Content not found · Gofile」
#            （正文 "This content does not exist ... removed after a period of inactivity"）
#   活页     title 三段演化：约 1s 'Gofile — Cloud Storage…' -> 2-3s 'Files · Gofile'
#            -> 4s 起稳定 '{contentId} · Gofile'。别信中间态，等按钮渲染
#   文件行   div.fm-row；按钮带 data-action：download / preview / item-menu；
#            真文件名在 item-menu 的 aria-label（"Actions for Kimiko.mp4"）
#   下载     点 button[data-action="download"] 直接触发浏览器下载事件——无广告
#            中转、无弹窗，suggested=真名，落点 store*.gofile.io 直链（临时 token）
#   体积     行文本里的人读值（"283 MB"），十进制显示
#
# /d/{id} 可能是单文件也可能是文件夹（文件夹就逐文件点）。子目录行没有
# download 按钮，本期只下直下文件、子目录跳过并在 note 里报数。
# 密码保护页未实测：留 input[type=password] 探测分支，命中即 needs_auth。

_GF_ROOT = "https://gofile.io"
_DEAD_MARK = "Content not found"
_DL_BTN = 'button[data-action="download"]'
_MENU_BTN = 'button[data-action="item-menu"]'
_SIZE_TEXT_RE = re.compile(r"([\d.]+)\s*(B|KB|MB|GB|TB)")
_SIZE_MULT = {"B": 1, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3, "TB": 1000 ** 4}
_WAIT_MS = 15000          # SPA 判定 + 渲染上限（实测 4s 内出结果）
_POLL_MS = 500


def parse_gf_url(url: str) -> str | None:
  """gofile URL -> contentId；认不出的形态返回 None"""
  m = re.match(r"^/d/([A-Za-z0-9]+)", urlsplit(url).path)
  return m.group(1) if m else None


def name_from_aria(aria_label: str) -> str:
  """item-menu 的 aria-label（"Actions for foo.mp4"）-> 文件名"""
  return re.sub(r"^Actions for\s+", "", aria_label or "").strip()


def parse_size_text(text: str) -> int | None:
  """行文本里的人读体积（"283 MB"，十进制）-> 近似字节；认不出返回 None"""
  m = _SIZE_TEXT_RE.search(text or "")
  if not m:
    return None
  try:
    return int(float(m.group(1)) * _SIZE_MULT[m.group(2).upper()])
  except ValueError:
    return None


async def _read_rows(page) -> list[dict]:
  """读文件行：[{name, size, dl_index}]，dl_index 是 download 按钮序号（点击用）"""
  rows = await page.evaluate(
      """() => {
        const btns = [...document.querySelectorAll('button[data-action="download"]')];
        return btns.map((b, i) => {
          const row = b.closest('.fm-row');
          const menu = row ? row.querySelector('button[data-action="item-menu"]') : null;
          return {dl_index: i, aria: menu ? menu.getAttribute('aria-label') : '',
                  text: row ? row.innerText : ''};
        });
      }""")
  out = []
  for r in rows:
    name = name_from_aria(r.get("aria") or "")
    if not name:
      continue
    out.append({"name": name,
                "size": parse_size_text(r.get("text") or ""),
                "dl_index": r["dl_index"]})
  return out


class GofileAdapter(HostAdapter):
  hosts = frozenset({"gofile.io"})

  async def _open(self, engine, url: str):
    """开 /d/{id} 页并等到 SPA 出结果。
    返回 ("dead", page, None) / ("ready", page, None) / ("needs_auth", page, None) /
    ("unknown", page, note)；page 恒非 None 时由调用方 close。"""
    page = await engine.context.new_page()
    try:
      await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
      await page.close()
      return "unknown", None, f"goto 失败: {e}"
    deadline = asyncio.get_event_loop().time() + _WAIT_MS / 1000
    while asyncio.get_event_loop().time() < deadline:
      title = await page.title()
      if _DEAD_MARK in title:
        return "dead", page, title
      try:
        if await page.locator(_DL_BTN).first.is_visible():
          return "ready", page, title
        if await page.locator("input[type=password]").first.is_visible():
          return "needs_auth", page, "密码保护"
      except Exception:
        pass   # 页面跳转瞬间 locator 可能失效，下轮再查
      await page.wait_for_timeout(_POLL_MS)
    return "unknown", page, f"{_WAIT_MS}ms 内未渲染出结果: {await page.title()!r}"

  async def probe(self, engine, url: str) -> ProbeResult:
    cid = parse_gf_url(url)
    if not cid:
      return ProbeResult("unknown", note=f"无法解析的 gofile 形态: {url}")
    async with engine.slot():
      state, page, note = await self._open(engine, f"{_GF_ROOT}/d/{cid}")
      if page is None:
        return ProbeResult("unknown", note=note)
      try:
        if state == "dead":
          return ProbeResult("dead", note=note[:60])
        if state == "needs_auth":
          return ProbeResult("needs_auth", note=note)
        if state != "ready":
          return ProbeResult("unknown", note=note)
        rows = await _read_rows(page)
        files = [{"name": r["name"], "size": r["size"], "url": None} for r in rows]
        total = sum(r["size"] or 0 for r in rows)
        return ProbeResult(
            "alive",
            filename=rows[0]["name"] if len(rows) == 1 else cid,
            size=rows[0]["size"] if len(rows) == 1 else (total or None),
            files=files,
            note=(f"{cid} 直下 {len(rows)} 文件"
                  + (f"，共约 {total/1e9:.1f}GB" if total else "")
                  + "（体积为页面近似值）"))
      finally:
        await page.close()

  async def download(self, engine, url: str, dest_dir: str) -> DownloadResult:
    cid = parse_gf_url(url)
    if not cid:
      return DownloadResult("failed", note=f"无法解析的 gofile 形态: {url}")
    async with engine.slot():
      state, page, note = await self._open(engine, f"{_GF_ROOT}/d/{cid}")
      if page is None:
        return DownloadResult("failed", note=note)
      try:
        if state == "dead":
          return DownloadResult("dead", note=note[:60])
        if state != "ready":
          return DownloadResult("failed", note=f"页面状态 {state}: {note}")
        rows = await _read_rows(page)
        os.makedirs(dest_dir, exist_ok=True)
        done = skipped = failed = 0
        msgs = []
        for r in rows:
          local = sanitize_filename(r["name"])
          dest = os.path.join(dest_dir, local)
          # 幂等：体积感知（行体积是页面近似值，3% 容差）；对不上是不同内容
          # 撞名，放行走引擎 token 第二把
          if os.path.exists(dest) and same_size_or_unknown(
              dest, r["size"], rel_tol=0.03):
            skipped += 1
            continue          # 已存在就不点按钮（0 流量）
          btn = page.locator(_DL_BTN).nth(r["dl_index"])
          try:
            async with page.expect_download(
                timeout=dl_wait_ms(r["size"], 60)) as dl_info:
              await btn.click()
            dl = await dl_info.value
            # 引擎收口落盘：检查名（aria-label）与 suggested 名可能不同源，
            # 且同夹不同行可能同名——token 掺文件名保证行间也分得开
            dest = await engine.save_download(
                dl, dest_dir,
                dl.suggested_filename or local,
                url_token(f"{url}#{r['name']}"))
            done += 1
          except (PWTimeoutError, Exception) as e:
            failed += 1
            msgs.append(f"{r['name']}: {e}")
        if failed:
          return DownloadResult("failed", note="; ".join(msgs)[:200])
        if done == 0:
          return DownloadResult("skipped", path=dest_dir,
                                note=f"{skipped} 文件已全部存在")
        return DownloadResult("downloaded", path=dest_dir,
                              note=f"新下 {done}，跳过 {skipped}，共 {len(rows)} 文件")
      finally:
        await page.close()
