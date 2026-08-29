"""调试 Dimmo：点进根下唯一的文件夹，看 URL/hash 变化（sharelink 前缀为何没出现）。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from python_general_lib.environment_setup.logging_setup import *  # noqa
import logging

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.baidu_pan.pages.shared_link_page import (
    SharedLinkPage, extract_share_prefix, current_hash_path)
from config import BAIDU_PAN_PROXY_SERVER

URL = "https://pan.baidu.com/s/1f5v3Q1q3eyZu6RfxRgQC2Q"
PWD = "yezi"


async def main():
    async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
        link_page = await SharedLinkPage.open(session.context, URL, password=PWD)
        page = link_page.page
        print("after open:")
        print("  url:  ", page.url)
        print("  hash: ", current_hash_path(page.url))
        print("  prefix:", extract_share_prefix(page.url))

        entries = await link_page.list_files()
        print("root entries:", [(e.name, e.is_dir) for e in entries])

        # 点进第一个目录
        await link_page.access_folder(entries[0].name)
        await page.wait_for_timeout(2000)
        print("after access_folder(%r):" % entries[0].name)
        print("  url:  ", page.url)
        print("  hash: ", current_hash_path(page.url))
        print("  prefix:", extract_share_prefix(page.url))

        entries2 = await link_page.list_files()
        print("sub entries:", [(e.name, e.is_dir) for e in entries2][:10])

        # 再进一层看 hash
        sub_dirs = [e for e in entries2 if e.is_dir]
        if sub_dirs:
            await link_page.access_folder(sub_dirs[0].name)
            await page.wait_for_timeout(2000)
            print("after access_folder(%r):" % sub_dirs[0].name)
            print("  url:  ", page.url)
            print("  hash: ", current_hash_path(page.url))
            print("  prefix:", extract_share_prefix(page.url))

        try:
            input("press enter to close")
        except EOFError:
            pass


asyncio.run(main())
