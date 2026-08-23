
"""gofile 活页 DOM 结构 + 点击行为观察（固定 1 条 AuxExhX6；1 次页面加载，
1 次点击->下载事件->立即 cancel，不拉数据）。"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

URL = "https://gofile.io/d/AuxExhX6"


def squeeze(s: str, n: int = 2600) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:n]


async def main():
  popups = []
  async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
    page = await engine.context.new_page()
    page.on("page", lambda p: popups.append(p.url) or asyncio.ensure_future(p.close()))
    try:
      await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
      # 等标题从壳渲染成内容（死链时是 'Content not found'，活页是 '{id} · Gofile'）
      for _ in range(20):
        t = await page.title()
        if "Content not found" in t or "Gofile" in t and t != "Files · Gofile":
          break
        await page.wait_for_timeout(500)
      print(f"title={await page.title()!r}")

      # 文件行结构：抓包含 Download 文本的按钮及其所在行容器
      btns = page.get_by_role("button", name=re.compile(r"^\s*Download\s*$", re.I))
      n = await btns.count()
      print(f"Download 按钮数: {n}")
      if n:
        first = btns.first
        info = await first.evaluate(
            """e => {
              const row = e.closest('li, tr, [class*=row], [class*=item]') || e.parentElement.parentElement;
              const path = [];
              let el = e;
              for (let i = 0; i < 4 && el; i++, el = el.parentElement)
                path.push(el.tagName + (el.className ? '.' + String(el.className).split(' ').slice(0,3).join('.') : ''));
              return {btnTag: e.tagName, btnCls: String(e.className).slice(0, 80),
                      rowHTML: row ? row.outerHTML : null, ancestry: path};
            }""")
        print(f"按钮: <{info['btnTag']} class={info['btnCls']!r}>")
        print(f"层级: {info['ancestry']}")
        print(f"行 HTML: {squeeze(info['rowHTML'] or '', 2200)}")

        # 点击行为：最小文件 Kimiko.mp4（69.2MB）-> 事件 -> cancel
        target = btns.nth(1)  # 行序：Kimiko decensored(283MB), Kimiko(69.2MB), ...
        row_text = squeeze(await target.evaluate("e => e.closest('li, tr, [class*=row], [class*=item]')?.innerText || ''"), 120)
        print(f"\n点击目标行: {row_text!r}")
        try:
          async with page.expect_download(timeout=25000) as dl_info:
            await target.click()
          dl = await dl_info.value
          print(f"下载事件 OK: suggested={dl.suggested_filename!r} url={dl.url[:120]}")
          await dl.cancel()
          print("已 cancel，未拉数据")
        except Exception as e:
          print(f"没等到下载事件: {e}")
          print(f"点击后 url={page.url} title={await page.title()!r}")
          body = await page.locator("body").inner_text()
          print(f"body: {squeeze(body, 800)}")
      if popups:
        print(f"弹出页(已关): {popups}")
    finally:
      await page.close()


asyncio.run(main())
