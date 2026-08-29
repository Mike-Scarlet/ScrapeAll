"""一次性调试：Dimmo(前缀发现失败) 与 山含(stable 超时) 两个分享页的真实状态。
只读：打开 -> 打印 url/title -> 截图 -> 尝试根列表 -> 尝试进第一个目录再读 URL。
"""
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

LINKS = {
    "Dimmo": ("https://pan.baidu.com/s/1f5v3Q1q3eyZu6RfxRgQC2Q", "yezi"),
    "ShanHan": ("https://pan.baidu.com/s/14Qek9KlgZX8jYAanzK9Ikw", "yezi"),
}
SHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "samples")


async def probe(session, name, url, pwd):
    print(f"\n########## {name}: {url}")
    try:
        page = await session.context.new_page()
        await page.goto(url, timeout=60000)
        await page.wait_for_load_state("domcontentloaded")
        if pwd:
            code = page.locator("#accessCode")
            try:
                await code.wait_for(state="visible", timeout=8000)
                await code.fill(pwd)
                await page.locator("#submitBtn").click()
                print("  password filled")
            except Exception:
                print("  no password form (or auto-filled)")
        await page.wait_for_timeout(8000)
        print(f"  title: {await page.title()!r}")
        print(f"  url:   {page.url}")
        print(f"  hash path: {current_hash_path(page.url)}")
        print(f"  prefix: {extract_share_prefix(page.url)}")
        await page.screenshot(path=os.path.join(SHOT_DIR, f"dbg_{name}.png"), full_page=False)
        # 根列表（直接扒 DOM，不走 stable 等待）
        html = await page.content()
        import re
        names = re.findall(r'title="([^"]+)"', html)
        print(f"  titles in dom (first 15): {names[:15]}")
        for sel in (".vdAfKMb", ".cazEfA", ".wPQwLCb", ".EOGexf", "a.filename"):
            n = await page.locator(sel).count()
            print(f"  selector {sel!r}: {n}")
        await page.close()
    except Exception as e:
        print(f"  !! {type(e).__name__}: {e}")


async def main():
    os.makedirs(SHOT_DIR, exist_ok=True)
    async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
        for name, (url, pwd) in LINKS.items():
            await probe(session, name, url, pwd)


asyncio.run(main())
