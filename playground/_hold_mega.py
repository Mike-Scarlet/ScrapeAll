
"""挂住浏览器窗口 10 分钟，供人工查看 mega 页面元素结构。
用户可在窗口里自由操作：右键、DevTools 检查元素。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

FOLDER = "https://mega.nz/folder/hS0XmIgL#afw2rN0BPH9pURsw7kIeTw"


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        page = await engine.context.new_page()
        await page.goto(FOLDER, wait_until="domcontentloaded", timeout=45000)
        print("已打开 mega folder 真紅 页，挂 10 分钟供人工查看", flush=True)
        for i in range(10):
            await asyncio.sleep(60)
            print(f"已挂 {i + 1} 分钟", flush=True)
        print("超时，关闭浏览器", flush=True)


asyncio.run(main())
