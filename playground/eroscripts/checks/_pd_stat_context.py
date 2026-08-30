# 摸 .stat 的 DOM 上下文：/d 页（E1Kk51Ls）与 /u 页（PV82t9fy）对照，
# 每个 .stat 打印自身 outerHTML + 父元素 innerText，找"体积"标签锚点
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from config import DOWNLOADER_PROXY_SERVER
from scrape_all.downloader.engine import DownloadEngine

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PAGES = [("d", "E1Kk51Ls"), ("u", "PV82t9fy")]


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        for form, pid in PAGES:
            async with engine.slot():
                page = await engine.context.new_page()
                try:
                    await page.goto(f"https://pixeldrain.com/{form}/{pid}",
                                    wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(1500)
                    print(f"\n== /{form}/{pid}  title={await page.title()!r}")
                    stats = page.locator(".stat")
                    n = await stats.count()
                    for i in range(n):
                        html = await stats.nth(i).evaluate("el => el.outerHTML")
                        parent = await stats.nth(i).evaluate(
                            "el => el.parentElement.innerText.trim().replace(/\\n/g, ' | ')")
                        print(f"  [{i}] {html[:120]}")
                        print(f"      parent: {parent[:120]}")
                finally:
                    await page.close()

asyncio.run(main())
