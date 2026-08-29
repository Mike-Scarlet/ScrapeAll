"""百度网盘转存编排执行器（真跑）。【已升包，留档】
正式入口 scripts/consume_posts.py（选点逻辑在 scrape_all/sites/baidu_pan/orchestrate.py，
真跑含 stat 2->3/6 流转）；本文件不标 stat，勿再用于全量。2026-08-24。

选点逻辑与 dry-run 完全共用（bd_orchestrate_dryrun.select_ops），
执行链路复用 save_executor：跳来源目录 -> 按名勾选 -> 保存弹窗 ->
navigate_to 逐级自动建缺失目录 -> 确认并等待成功提示。

用法：
  python playground/baidu_pan/orchestrate/bd_orchestrate.py --smoke            # 冒烟集 4 链接（覆盖全部操作形态）
  python playground/baidu_pan/orchestrate/bd_orchestrate.py --ids 216571,219782
  python playground/baidu_pan/orchestrate/bd_orchestrate.py                    # 全部 stat=2（30+ 链接，慢）
  --yes 跳过人工确认（自动化场景用；默认在第一个非空计划前要输 yes）

流程（逐链接流水，不攒页面）：每条链接 walk+选点 -> 打印计划 -> 立刻执行 -> 关页，
进入下一条。全量 35 链接若先把页面全打开再统一执行，浏览器要同时挂 30+ 个分享页，
内存压力下标签可能被丢弃；流水式任意时刻只有当前链接的页面，且中途挂掉时
已完成的链接不受影响（重跑用 --ids 指定剩余即可）。

TODO（方案待定，先记着）：
  1. 逻辑升包：select_ops/make_policy/make_target_for/load_* 还在 playground
     （bd_orchestrate_dryrun.py + 本文件），流程稳定后升入
     scrape_all.sites.baidu_pan，纯逻辑单测（_logic_selftest.py）跟着搬。
  2. 消费标记：转存成功的帖子把 cangku.db stat 2->3，重跑天然排除已转存；
     现在只能靠 --ids 手动剔除（本次全量即剔了 ink+ 验证帖）。
     要定：标记粒度（帖子级 or 链接级）、失败 op 是否阻止升级、
     死链/部分失败帖子留在 2 还是单列。
  3. 死链补偿：山含 225111 分享已删（链接不存在），等仓库更新帖子里的
     链接后补跑；可给 load_share_links 加包含死链的入口，或靠 2 的
     stat 流转 + 仓库侧重抓自然覆盖。
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
from scrape_all.sites.baidu_pan.save_plan import format_plan
from scrape_all.sites.baidu_pan.save_executor import execute_save_plan, format_results
from scrape_all.sites.baidu_pan.walker import ShareWalker
from config import BAIDU_PAN_PROXY_SERVER
from playground.baidu_pan.orchestrate.bd_orchestrate_dryrun import (
    TARGET_BASE, load_local_months, load_share_links, make_policy, select_ops)

# 冒烟集：Solis 新作者整目录（根级 op）/ ink+ 月份目录单元 / AS109 散文件 /
# Erio 多 op + 重抓月精确补齐（月目录内单文件）
SMOKE_IDS = ["225540", "219782", "216571", "222356"]


def emit(line=""):
  print(line)


async def close_quietly(link_page):
  # 执行期 save_executor 从第 2 个 op 起换新页并关掉原页面，这里可能已关过
  try:
    await link_page.page.close()
  except Exception:
    pass


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
  emit(f"本地库作者 {len(local)} 个；分享链接 {len(links)} 个")

  ok_ops = total_ops = 0
  done_posts = []      # 该帖所有 op 都成功
  partial_posts = []   # 部分 op 失败/不确定
  failed_posts = []    # walk/打开就失败，一个 op 都没执行

  async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
    confirmed = auto_yes
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
        failed_posts.append(f"{link['post_id']} (打开/walk 失败)")
        continue

      ops = await select_ops(link_page, tree, link, local, emit)

      if not ops:
        emit("  （无可转存内容，跳过）")
        await close_quietly(link_page)
        await asyncio.sleep(2)
        continue

      print("\n--- save plan")
      print(format_plan(ops))

      if not confirmed:
        try:
          answer = input(f"\npost {link['post_id']} 计划 {len(ops)} 项，目标根 {TARGET_BASE}，"
                         f"输入 yes 开始执行（后续链接不再确认）: ")
        except EOFError:
          answer = ""
        if answer.strip() != "yes":
          print("未确认，退出")
          return
        confirmed = True

      async def page_factory(link=link):
        # 实测同页"转存成功后再 goto"会确定性挂死，从第 2 个 op 起每个 op 换新页
        return await SharedLinkPage.open(session.context, link["url"],
                                         password=link["pwd"])

      try:
        results = await execute_save_plan(link_page, ops, page_factory=page_factory)
      except Exception as e:
        logging.error(f"execute crashed ({link['post_id']}): {type(e).__name__}: {e}")
        results = []

      print(format_results(results))
      total_ops += len(ops)
      n_ok = sum(1 for r in results if r.ok)
      ok_ops += n_ok
      if n_ok == len(ops):
        done_posts.append(link["post_id"])
      else:
        partial_posts.append(f"{link['post_id']} ({n_ok}/{len(ops)} op 成功)")

      await close_quietly(link_page)
      await asyncio.sleep(3)   # 链接间停一下，降低风控风险

    print(f"\n=== 汇总: 操作 {ok_ops}/{total_ops} 成功；帖子 全成功 {len(done_posts)}"
          f" + 部分失败 {len(partial_posts)} + walk 失败 {len(failed_posts)}"
          f" / 共 {len(links)}")
    if partial_posts:
      print("部分失败: " + ", ".join(partial_posts))
    if failed_posts:
      print("walk 失败: " + ", ".join(failed_posts))

    if not auto_yes:
      try:
        input("\ndone, press enter to close browser ")
      except EOFError:
        pass


if __name__ == "__main__":
  asyncio.run(main())
