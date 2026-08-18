"""探针 v2：真保存一轮后 hash goto 是否失效 + 恢复手段验证。

冒烟失败形态：op1 真转存成功后，op2/op3 的 goto 10s 内无 share/list 请求、
内容不变、勾选等 30s 超时 —— 怀疑保存确认流程让 SPA 路由不再响应 hash 变化。
本脚本做一次最小真保存（/Erio/2025/25.08 里的 25.08 NPC.mp4，未转存过的小文件，
存到 /扒/_probe_tmp —— 验证完人工删掉即可），然后：
  1. goto /Erio/2026 -> 列目录验证 26.01 在
  2. 失败则：按 Escape + 等 2s -> 重试 goto 验证
  3. 仍失败则：page.reload() -> 重试 goto 验证
每步打印 hash 与列表，失败截图。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *  # noqa
import logging

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.baidu_pan.pages.save_dialog import SaveDialog
from scrape_all.sites.baidu_pan.pages.shared_link_page import SharedLinkPage
from config import BAIDU_PAN_PROXY_SERVER

ERIO = "https://pan.baidu.com/s/19kvyZHU3A-92bMmSOoDYNw"
ERIO_PWD = "yezi"
SAVE_TARGET = "/扒/_probe_tmp"
SHOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


async def list_names(link_page):
  entries = await link_page.list_files()
  return [e.name for e in entries]


async def check_goto(link_page, path, expect, tag):
  """goto + 列目录，验证 expect 都在；打印详情，返回是否成功"""
  try:
    await link_page.goto_path(path)
  except Exception as e:
    print(f"[{tag}] goto_path 抛异常: {type(e).__name__}: {e}")
    return False
  try:
    names = await list_names(link_page)
  except Exception as e:
    print(f"[{tag}] list_files 抛异常: {type(e).__name__}: {e}")
    return False
  h = link_page.page.url.split("#", 1)[1] if "#" in link_page.page.url else "(no hash)"
  print(f"[{tag}] hash 已到目标: {path in __import__('urllib.parse', fromlist=['unquote']).unquote(h)}")
  print(f"[{tag}] list ({len(names)}): {', '.join(names[:8])}")
  missing = [n for n in expect if n not in names]
  print(f"[{tag}] missing: {missing or '无（成功）'}")
  return not missing


async def main():
  async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
    link_page = await SharedLinkPage.open(session.context, ERIO, password=ERIO_PWD)
    dialog = SaveDialog(link_page.page)
    shot = os.path.join(SHOT, "_debug_goto2_fail.png")
    try:
      # ---- 最小真保存：25.08 NPC.mp4 -> /扒/_probe_tmp
      await link_page.goto_path("/Erio/2025/25.08")
      print("保存前列表:", await list_names(link_page))
      await link_page.select_files(["25.08 NPC.mp4"])
      await dialog.open()
      nav_ok, nav_msg = await dialog.navigate_to(SAVE_TARGET)
      print(f"navigate: {nav_ok} ({nav_msg})")
      if not nav_ok:
        print("!! 导航失败，放弃保存，直接测 goto")
      else:
        confirmed = await dialog.confirm()
        print(f"confirm: {confirmed}")
      try:
        if await dialog.is_open():
          await dialog.cancel()
      except Exception as e:
        print(f"cancel: {e}")

      # ---- 保存后立刻 goto
      ok = await check_goto(link_page, "/Erio/2026", ["26.01", "26.02"], "A-保存后直接goto")
      if ok:
        print("\n结论：保存后 goto 正常（未能复现冒烟问题）")
        return

      # ---- 恢复手段 1：Escape + 重试
      await link_page.page.keyboard.press("Escape")
      await asyncio.sleep(2)
      ok = await check_goto(link_page, "/Erio/2026", ["26.01", "26.02"], "B-Escape后goto")
      if ok:
        print("\n结论：Escape 可恢复 —— 执行器在 op 间补一个 Escape 即可")
        return

      # ---- 恢复手段 2：整页 reload 后 goto
      await link_page.page.reload()
      await link_page.page.wait_for_load_state("domcontentloaded")
      await asyncio.sleep(3)
      ok = await check_goto(link_page, "/Erio/2026", ["26.01", "26.02"], "C-reload后goto")
      print("\n结论: " + ("reload 可恢复" if ok else "reload 也不行，需进一步排查"))
    except Exception:
      import traceback
      traceback.print_exc()
      await link_page.page.screenshot(path=shot)
      print(f"失败截图: {shot}")
    finally:
      await link_page.page.close()


asyncio.run(main())
