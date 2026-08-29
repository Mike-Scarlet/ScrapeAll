"""补跑冒烟时失败的 Erio 两个 op（用加固后的执行器验证恢复能力）。

冒烟计划里 Erio 三个 op：op1 已成功（25.09-25.12 -> /扒/20260818/[yejiang]/Erio/2025），
op2/op3 超时失败。这里只构建这两个 op 原样重跑：
  /Erio/2025/25.08 : ["25.08 虎克.mp4"] -> /扒/20260818/[yejiang]/Erio/2025/25.08
  /Erio/2026      : ["26.01", "26.02"] -> /扒/20260818/[yejiang]/Erio/2026
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

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
    SaveOp("/Erio/2025/25.08", ["25.08 虎克.mp4"],
           "/扒/20260818/[yejiang]/Erio/2025/25.08"),
    SaveOp("/Erio/2026", ["26.01", "26.02"],
           "/扒/20260818/[yejiang]/Erio/2026"),
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
