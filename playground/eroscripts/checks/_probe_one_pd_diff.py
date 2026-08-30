# 追查：E1Kk51Ls 的 /d、/u、/l 三种形态各开真页面读 title + .stat（只读不开下载）
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from config import DOWNLOADER_PROXY_SERVER
from scrape_all.downloader.engine import DownloadEngine
from scrape_all.downloader.adapters.pixeldrain import parse_size_text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PID = "E1Kk51Ls"
FORMS = [f"/d/{PID}", f"/u/{PID}", f"/l/{PID}"]


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        for path in FORMS:
            async with engine.slot():
                page = await engine.context.new_page()
                try:
                    resp = await page.goto(f"https://pixeldrain.com{path}",
                                           wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(1200)
                    title = await page.title()
                    stats = await page.locator(".stat").all_inner_texts()
                    print(f"{path}  http={resp.status if resp else '?'}  title={title!r}  stat={stats}")
                except Exception as e:
                    print(f"{path}  异常: {e}")
                finally:
                    await page.close()

asyncio.run(main())
