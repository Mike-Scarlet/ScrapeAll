
"""gofile 页面观察（固定 3 条，无遍历；3 次页面加载，0 下载）。
每条打印：http 状态 / 跳转后 URL / title / 正文摘录 / 按钮和链接结构。"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

URLS = [
    "https://gofile.io/d/UYEU7v",    # topic 21811，name "Gofile - Cloud Storage Made Simple"
    "https://gofile.io/d/iCM2zq",    # topic 35882
    "https://gofile.io/d/AuxExhX6",  # topic 332049，最新一条
]
SETTLE_MS = 3000   # gofile 是 Vue SPA，给足渲染时间


def squeeze(s: str, n: int = 1100) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:n]


async def observe(engine, url: str):
    page = await engine.context.new_page()
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(SETTLE_MS)
        print(f"\n===== {url}")
        print(f"http={resp.status if resp else '?'}  final_url={page.url}")
        title = await page.title()
        print(f"title={title!r}")
        body = await page.locator("body").inner_text()
        print(f"body: {squeeze(body)}")
        btns = await page.locator("button, a.btn, a[download], a[href*='/dl/']").all()
        print(f"按钮/下载类元素 {len(btns)} 个:")
        for b in btns[:20]:
            try:
                txt = squeeze(await b.inner_text(), 40)
                tag = await b.evaluate("e => e.tagName + '.' + (e.className||'') + '|' + (e.getAttribute('href')||'')")
                print(f"   {tag}  text={txt!r}")
            except Exception:
                pass
    finally:
        await page.close()


async def main():
  async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
    for u in URLS:
      try:
        await observe(engine, u)
      except Exception as e:
        print(f"\n===== {u}\n失败: {e}")
  print("\n完成")


asyncio.run(main())
