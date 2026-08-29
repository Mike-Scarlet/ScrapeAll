"""看一眼 Erio 分享页当前的真实状态（怀疑限流/验证码）：开页 -> 截图 -> 稳定选择器探针。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from python_general_lib.environment_setup.logging_setup import *  # noqa
import logging

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.baidu_pan.pages.shared_link_page import SharedLinkPage
from config import BAIDU_PAN_PROXY_SERVER

ERIO = "https://pan.baidu.com/s/19kvyZHU3A-92bMmSOoDYNw"
ERIO_PWD = "yezi"
SHOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data")


async def main():
  async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
    link_page = await SharedLinkPage.open(session.context, ERIO, password=ERIO_PWD)
    page = link_page.page
    try:
      await asyncio.sleep(5)
      print("title:", await page.title())
      print("url:", page.url)
      for sel in (".cazEfA", ".wPQwLCb", ".vdAfKMb"):
        cnt = await page.locator(sel).count()
        vis = await page.locator(sel).first.is_visible() if cnt else False
        print(f"selector {sel!r}: count={cnt} first_visible={vis}")
      await page.screenshot(path=os.path.join(SHOT, "_peek_erio.png"))
      print("截图: data/_peek_erio.png")
    finally:
      await page.close()


asyncio.run(main())
