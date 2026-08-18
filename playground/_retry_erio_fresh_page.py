"""假设验证 + 补欠账：新开页面执行 Erio 欠着的 op（/Erio/2026 -> 26.01/26.02）。

已有证据链：同页"转存成功后 goto"会确定性挂死（三级恢复也救不回），
而新开页面后的第一个 op 从未失败过。若本脚本成功 -> 把"新开页"作为
执行器的第 4 级恢复手段。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *  # noqa
import logging

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.baidu_pan.pages.shared_link_page import SharedLinkPage
from scrape_all.sites.baidu_pan.save_plan import SaveOp
from scrape_all.sites.baidu_pan.save_executor import execute_save_plan, format_results
from config import BAIDU_PAN_PROXY_SERVER

ERIO = "https://pan.baidu.com/s/19kvyZHU3A-92bMmSOoDYNw"
ERIO_PWD = "yezi"

OPS = [
    SaveOp("/Erio/2026", ["26.01", "26.02"], "/扒/20260818/[yejiang]/Erio/2026"),
]


async def main():
  async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
    link_page = await SharedLinkPage.open(session.context, ERIO, password=ERIO_PWD)
    try:
      results = await execute_save_plan(link_page, OPS)
      print()
      print(format_results(results))
    finally:
      await link_page.page.close()


asyncio.run(main())
