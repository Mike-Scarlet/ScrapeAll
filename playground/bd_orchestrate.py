"""百度网盘转存编排执行器（真跑）。

选点逻辑与 dry-run 完全共用（bd_orchestrate_dryrun.select_ops），
执行链路复用 save_executor：跳来源目录 -> 按名勾选 -> 保存弹窗 ->
navigate_to 逐级自动建缺失目录 -> 确认并等待成功提示。

用法：
  python playground/bd_orchestrate.py --smoke            # 冒烟集 4 链接（覆盖全部操作形态）
  python playground/bd_orchestrate.py --ids 216571,219782
  python playground/bd_orchestrate.py                    # 全部 stat=2（30+ 链接，慢）
  --yes 跳过人工确认（自动化场景用；默认要输 yes）
流程：全部链接先 walk+选点并打印计划（页面保持打开）-> 确认 -> 逐链接执行 -> 汇总。
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
from scrape_all.sites.baidu_pan.save_plan import format_plan
from scrape_all.sites.baidu_pan.save_executor import execute_save_plan, format_results
from scrape_all.sites.baidu_pan.walker import ShareWalker
from config import BAIDU_PAN_PROXY_SERVER
from playground.bd_orchestrate_dryrun import (
    TARGET_BASE, load_local_months, load_share_links, make_policy, select_ops)

# 冒烟集：Solis 新作者整目录（根级 op）/ ink+ 月份目录单元 / AS109 散文件 /
# Erio 多 op + 重抓月精确补齐（月目录内单文件）
SMOKE_IDS = ["225540", "219782", "216571", "222356"]


def emit(line=""):
  print(line)


async def main():
  args = sys.argv[1:]
  use_smoke = "--smoke" in args
  auto_yes = "--yes" in args

  ids, limit = None, None
  for i, a in enumerate(args):
    if a.startswith("--ids="):
      ids = [x for x in a[6:].split(",") if x]
    elif a == "--ids" and i + 1 < len(args):
      ids = [x for x in args[i + 1].split(",") if x]
    elif a.startswith("--limit="):
      limit = int(a[7:])

  links = load_share_links(ids=SMOKE_IDS if use_smoke else ids, limit=limit)
  if not links:
    print("没有可处理的链接")
    return

  local = load_local_months()
  emit(f"目标根: {TARGET_BASE}")
  emit(f"本地库作者 {len(local)} 个；分享链接 {len(links)} 个\n")

  plans = []   # (link, SharedLinkPage, ops)；页面保持打开，执行阶段直接复用
  async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
    for li, link in enumerate(links, 1):
      print(f"\n=== [{li}/{len(links)}] post {link['post_id']}  {link['title'][:40]}")

      # open + walk 整体重试一次（与 dry-run 相同策略）
      tree = None
      link_page = None
      policy = make_policy(local, link["box_title"])
      for attempt in (1, 2):
        try:
          link_page = await SharedLinkPage.open(session.context, link["url"],
                                                password=link["pwd"])
          tree = await ShareWalker(link_page).walk(policy)
          break
        except Exception as e:
          msg = f"{type(e).__name__}: {e}"
          if link_page is not None:
            await link_page.page.close()
            link_page = None
          dead = "share invalid" in str(e)
          if attempt == 1 and not dead:
            logging.warning(f"retry ({link['post_id']}): {msg}")
            await asyncio.sleep(3)
          else:
            emit(f"  !! failed, skip: {msg}")
            break
      if tree is None:
        continue

      ops = await select_ops(link_page, tree, link, local, emit)
      plans.append((link, link_page, ops))
      print("\n--- save plan")
      print(format_plan(ops))
      await asyncio.sleep(2)   # 链接间停一下，降低风控风险

    total = sum(len(ops) for _, _, ops in plans)
    if total == 0:
      print("\n没有可转存的内容（计划为空），退出")
      return

    if not auto_yes:
      try:
        answer = input(f"\n共 {len(plans)} 个链接 {total} 个转存操作，"
                       f"目标根 {TARGET_BASE}，确认无误输入 yes 开始执行: ")
      except EOFError:
        answer = ""
      if answer.strip() != "yes":
        print("未确认，什么都不做，退出")
        return

    ok_ops = 0
    for link, link_page, ops in plans:
      if not ops:
        await link_page.page.close()
        continue
      print(f"\n=== saving post {link['post_id']}  {link['title'][:40]}")

      async def page_factory(link=link):
        # 实测同页"转存成功后再 goto"会确定性挂死，从第 2 个 op 起每个 op 换新页
        return await SharedLinkPage.open(session.context, link["url"],
                                         password=link["pwd"])

      results = await execute_save_plan(link_page, ops, page_factory=page_factory)
      print(format_results(results))
      ok_ops += sum(1 for r in results if r.ok)
      await link_page.page.close()

    print(f"\n完成: {ok_ops}/{total} 个操作成功（失败/不确定的见上方 note，需人工核对）")

    try:
      input("\ndone, press enter to close browser ")
    except EOFError:
      pass


if __name__ == "__main__":
  asyncio.run(main())
