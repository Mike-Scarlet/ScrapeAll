
"""gofile 重定向诊断（固定 1 条 AuxExhX6；1 次页面加载，0 点击 0 下载）"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

URL = "https://gofile.io/d/AuxExhX6"


def squeeze(s: str, n: int = 600) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:n]


async def main():
  async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
    page = await engine.context.new_page()
    redirects = []
    page.on("request", lambda r: redirects.append((r.resource_type, r.url[:120]))
            if r.resource_type == "document" else None)
    try:
      resp = await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
      print(f"goto: status={resp.status if resp else '?'} "
            f"resp.url={resp.url if resp else '?'}")
      print(f"redirect chain(document): ")
      for rt, u in redirects:
        print(f"   {u}")
      for i in range(15):
        t = await page.title()
        print(f"[{(i+1)*1.0:4.1f}s] url={page.url[:80]}  title={t!r}")
        if i in (0, 14):
          body = await page.locator("body").inner_text()
          print(f"   body: {squeeze(body)}")
        await page.wait_for_timeout(1000)
      btns = page.get_by_role("button", name=re.compile(r"download", re.I))
      print(f"Download 按钮数: {await btns.count()}")
    finally:
      await page.close()


asyncio.run(main())
