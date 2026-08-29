"""只读探针：定位'保存弹窗交互一轮后 hash goto 失效'。

Erio 冒烟失败的形态：同页第 1 个 op 成功后，第 2/3 个 op 的 goto_path 没有真正
导航（稳定等待通过但内容还是旧目录），select 等 30s 超时。
本脚本不勾选不转存，只做 goto + 列目录 + 开/关保存弹窗，逐步复现：
  1. 连续 goto（无弹窗交互）是否正常
  2. open+cancel 一轮弹窗后 goto 是否失效
  3. 再来一轮 open+cancel 后 goto
每步打印 page.url 的 hash 和列出的名字，失败截图。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from python_general_lib.environment_setup.logging_setup import *  # noqa
import logging

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.baidu_pan.pages.save_dialog import SaveDialog
from scrape_all.sites.baidu_pan.pages.shared_link_page import SharedLinkPage
from config import BAIDU_PAN_PROXY_SERVER

ERIO = "https://pan.baidu.com/s/19kvyZHU3A-92bMmSOoDYNw"
ERIO_PWD = "yezi"
SHOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data")


def show(tag, page, names):
  h = page.url.split("#", 1)[1] if "#" in page.url else "(no hash)"
  print(f"\n[{tag}] url hash: {h}")
  print(f"[{tag}] list ({len(names)}): {', '.join(n.name for n in names[:8])}")


async def step_goto(link_page, path, tag, expect):
  await link_page.goto_path(path)
  entries = await link_page.list_files()
  show(tag, link_page.page, entries)
  got = [e.name for e in entries]
  missing = [n for n in expect if n not in got]
  print(f"[{tag}] expect missing: {missing or '无（全部命中）'}")
  return not missing


async def main():
  async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
    link_page = await SharedLinkPage.open(session.context, ERIO, password=ERIO_PWD)
    dialog = SaveDialog(link_page.page)
    try:
      ok1 = await step_goto(link_page, "/Erio/2025", "1-连续goto-2025", ["25.09", "25.08"])
      ok2 = await step_goto(link_page, "/Erio/2026", "2-连续goto-2026", ["26.01", "26.02"])
      ok3 = await step_goto(link_page, "/Erio/2025/25.08", "3-连续goto-25.08", ["25.08 虎克.mp4"])

      print("\n--- 弹窗 open + cancel 一轮")
      await dialog.open()
      await asyncio.sleep(1)
      await dialog.cancel()
      await asyncio.sleep(1)
      ok4 = await step_goto(link_page, "/Erio/2026", "4-弹窗cancel后-goto-2026", ["26.01", "26.02"])

      print("\n--- 再来一轮 open + cancel")
      await dialog.open()
      await asyncio.sleep(1)
      await dialog.cancel()
      await asyncio.sleep(1)
      ok5 = await step_goto(link_page, "/Erio/2025/25.08", "5-二轮弹窗后-goto-25.08", ["25.08 虎克.mp4"])

      print("\n结果:", {"连续goto": ok1 and ok2 and ok3, "弹窗cancel后": ok4, "二轮弹窗后": ok5})
    except Exception as e:
      import traceback
      traceback.print_exc()
      shot = os.path.join(SHOT, "_debug_goto_fail.png")
      await link_page.page.screenshot(path=shot)
      print(f"失败截图: {shot}")
    finally:
      await link_page.page.close()


asyncio.run(main())
