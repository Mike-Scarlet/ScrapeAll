
"""gofile 活页 DOM 导出 + 点击->事件->cancel（固定 1 条 AuxExhX6；1 次页面加载，
1 次点击不拉数据）。等待条件改为等按钮渲染，不再信 title 中间态。"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import TimeoutError as PWTimeoutError

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

URL = "https://gofile.io/d/AuxExhX6"


def squeeze(s: str, n: int = 2400) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:n]


async def main():
  popups = []
  async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
    page = await engine.context.new_page()
    page.on("page", lambda p: (popups.append(p.url),
                               asyncio.ensure_future(p.close())) and None)
    try:
      await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
      btns = page.get_by_role("button", name=re.compile(r"^\s*Download\s*$", re.I))
      try:
        await btns.first.wait_for(state="visible", timeout=15000)
      except PWTimeoutError:
        t = await page.title()
        body = await page.locator("body").inner_text()
        print(f"15s 没等到 Download 按钮: title={t!r}")
        print(f"body: {squeeze(body, 800)}")
        return
      print(f"title={await page.title()!r}  Download 按钮数={await btns.count()}")

      info = await btns.first.evaluate(
          """e => {
            const row = e.closest('li, tr, [class*=row], [class*=item]') || e.parentElement.parentElement;
            const path = [];
            let el = e;
            for (let i = 0; i < 4 && el; i++, el = el.parentElement)
              path.push(el.tagName + (el.className ? '.' + String(el.className).split(' ').slice(0,3).join('.') : ''));
            return {btnCls: String(e.className).slice(0, 100),
                    rowTag: row ? row.tagName : null,
                    rowCls: row ? String(row.className).slice(0, 100) : null,
                    rowHTML: row ? row.outerHTML : null, ancestry: path};
          }""")
      print(f"按钮 class: {info['btnCls']!r}")
      print(f"行容器: <{info['rowTag']} class={info['rowCls']!r}>")
      print(f"层级: {info['ancestry']}")
      print(f"行 HTML: {squeeze(info['rowHTML'] or '')}")

      # 点击第 2 行（Kimiko.mp4 69.2MB 最小）-> 下载事件 -> 立即 cancel
      target = btns.nth(1)
      row_text = squeeze(await target.evaluate(
          "e => (e.closest('li, tr, [class*=row], [class*=item]') || e.parentElement.parentElement)?.innerText || ''"), 150)
      print(f"\n点击目标行: {row_text!r}")
      try:
        async with page.expect_download(timeout=25000) as dl_info:
          await target.click()
        dl = await dl_info.value
        print(f"下载事件 OK: suggested={dl.suggested_filename!r}")
        print(f"   url={dl.url[:140]}")
        await dl.cancel()
        print("已 cancel，未拉数据")
      except Exception as e:
        print(f"没等到下载事件: {e}")
        print(f"点击后 url={page.url} title={await page.title()!r}")
      if popups:
        print(f"弹出页(已关): {popups}")
    finally:
      await page.close()


asyncio.run(main())
