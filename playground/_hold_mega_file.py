
"""挂住浏览器 10 分钟：mega file 页（isami_ride，已落盘过），供人工指认
大下载按钮等元素。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

FILEPG = "https://mega.nz/file/7hB2WbaD#KuV2r-Wa9CuaZXYEdW93na8vDTzGIqvuV6IbFBpgxt4"


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        page = await engine.context.new_page()
        await page.goto(FILEPG, wait_until="domcontentloaded", timeout=45000)
        print("已打开 mega file 页（isami_ride），挂 10 分钟供人工指认", flush=True)
        for i in range(10):
            await asyncio.sleep(60)
            print(f"已挂 {i + 1} 分钟", flush=True)
        print("超时，关闭浏览器", flush=True)


asyncio.run(main())
