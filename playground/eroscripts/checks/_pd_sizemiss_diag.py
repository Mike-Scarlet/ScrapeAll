# 冒烟异常追查：ry28cRGM probe 体积读成 801B、实际 803MB——看它的 .stat 块
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from config import DOWNLOADER_PROXY_SERVER
from scrape_all.downloader.engine import DownloadEngine

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        async with engine.slot():
            page = await engine.context.new_page()
            try:
                await page.goto("https://pixeldrain.com/d/ry28cRGM",
                                wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1500)
                print(f"title = {await page.title()!r}")
                blocks = await page.locator(".stat").evaluate_all(
                    "els => els.map(e => e.parentElement.innerText.trim())")
                print(f".stat 父块共 {len(blocks)} 个:")
                for i, b in enumerate(blocks):
                    print(f"  [{i}] {b.replace(chr(10), ' | ')}")
            finally:
                await page.close()

asyncio.run(main())
