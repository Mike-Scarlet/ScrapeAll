"""探针 v3：细粒度定位"保存成功后同页 goto 挂死"的精确环节 + 候选修复验证。

已知（_retry_erio_ops 复跑）：op1 保存成功后，op2 的 goto 三级恢复全灭：
  尝试1/2: Timeout 30s（疑似 page.goto 导航超时）；尝试3: reload 后 10s 稳定等待超时。
本脚本：保存一个小文件到 /扒/_probe_tmp（重复转存，临时目录验证后删），
然后逐步：打印 URL -> goto 计时 -> title -> 列表 -> 失败截图；
再测候选修复：page.evaluate 直接改 location.hash 是否能让路由动起来。
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from python_general_lib.environment_setup.logging_setup import *  # noqa
import logging

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

from playwright.async_api import TimeoutError as PWTimeout
from scrape_all.browser.session import BrowserSession
from scrape_all.sites.baidu_pan.pages.save_dialog import SaveDialog
from scrape_all.sites.baidu_pan.pages.shared_link_page import SharedLinkPage
from config import BAIDU_PAN_PROXY_SERVER

ERIO = "https://pan.baidu.com/s/19kvyZHU3A-92bMmSOoDYNw"
ERIO_PWD = "yezi"
SHOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data")


async def snap(page, tag):
  shot = os.path.join(SHOT, f"_probe3_{tag}.png")
  await page.screenshot(path=shot)
  print(f" 截图: {shot}")


async def timed(coro, label, page=None, tag=None):
  t = time.monotonic()
  try:
    r = await asyncio.wait_for(coro, timeout=45)
    print(f" [{label}] ok ({time.monotonic() - t:.1f}s)")
    return r, True
  except Exception as e:
    print(f" [{label}] FAIL {time.monotonic() - t:.1f}s: {type(e).__name__}: {e}")
    if page is not None and tag:
      await snap(page, tag)
    return None, False


async def main():
  async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
    link_page = await SharedLinkPage.open(session.context, ERIO, password=ERIO_PWD)
    page = link_page.page
    dialog = SaveDialog(page)
    try:
      print("\n== 1. 就位 /Erio/2025/25.08 并做一次真保存（-> /扒/_probe_tmp）")
      await link_page.goto_path("/Erio/2025/25.08")
      await link_page.select_files(["25.08 NPC.mp4"])
      await dialog.open()
      await dialog.navigate_to("/扒/_probe_tmp")
      print(" confirm:", await dialog.confirm())
      try:
        if await dialog.is_open():
          await dialog.cancel()
      except Exception as e:
        print(" cancel:", e)

      print("\n== 2. 保存后页面状态")
      print(" url:", page.url)
      print(" title:", await page.title())

      print("\n== 3. goto /Erio/2026（分步计时）")
      print(" 3a. page.goto 深链")
      base = page.url.split("#")[0]
      from urllib.parse import quote
      internal = "/sharelink1103162513293-479188374003283/Erio/2026"
      url = f"{base}#list/path={quote(internal, safe='')}&parentPath={quote('/sharelink1103162513293-479188374003283/Erio', safe='')}"
      print(" 目标 url:", url)
      _, ok = await timed(page.goto(url), "page.goto", page, "goto_fail")
      if ok:
        print(" 3b. title:", await page.title())
        print(" 3c. 稳定等待+列表")
        _, ok2 = await timed(link_page.list_files(), "list_files", page, "list_fail")
        if ok2:
          names = [e.name for e in (await link_page.list_files())]
          print(" 列表:", names)

      print("\n== 4. 候选修复：evaluate 改 location.hash")
      try:
        await page.evaluate(
            "h => { location.hash = h }",
            f"list/path={quote(internal, safe='')}&parentPath={quote('/sharelink1103162513293-479188374003283/Erio', safe='')}")
        await asyncio.sleep(3)
        print(" hash 赋值后 url:", page.url)
        _, ok3 = await timed(link_page.list_files(), "list_files(hash)", page, "hash_list_fail")
        if ok3:
          entries = await link_page.list_files()
          print(" 列表:", [e.name for e in entries])
      except Exception as e:
        print(" evaluate 失败:", type(e).__name__, e)

    finally:
      await link_page.page.close()


asyncio.run(main())
