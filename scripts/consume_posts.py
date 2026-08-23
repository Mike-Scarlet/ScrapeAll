
import argparse, asyncio, datetime, json, logging, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
import logging
logging.basicConfig(
  level=logging.NOTSET,
  format="[%(asctime)s] %(message)s",
)

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.baidu_pan.orchestrate import (
  ShareLink, load_local_months, make_policy, select_ops,
)
from scrape_all.sites.baidu_pan.pages.shared_link_page import SharedLinkPage
from scrape_all.sites.baidu_pan.save_plan import format_plan
from scrape_all.sites.baidu_pan.save_executor import execute_save_plan, format_results
from scrape_all.sites.baidu_pan.tree import format_tree
from scrape_all.sites.baidu_pan.walker import ShareWalker
from scrape_all.sites.cangku.store import PostStore
from config import BAIDU_PAN_PROXY_SERVER

# consume 阶段入口：cangku stat=2 帖子的百度盘分享 -> 增量转存到自己网盘。
#
#   python scripts/consume_posts.py                 # dry-run 全量：walk+选点+打印计划，不动 stat
#   python scripts/consume_posts.py --smoke         # 冒烟集 4 帖（覆盖全部操作形态）
#   python scripts/consume_posts.py --ids=228416,225111
#   python scripts/consume_posts.py --limit=3
#   python scripts/consume_posts.py --execute       # 真跑，首个非空计划前要输 yes
#   python scripts/consume_posts.py --execute --yes # 全自动
#
# 选点：分享根目录按作者分道，本地库（local_library.db）无记录的作者整目录全转存；
# 已匹配作者增量对比（重抓最后月 + 未覆盖月，重抓月只补本地没有的子项）。
# 目标统一落 /扒/<运行日期>/[yejiang]/…，已匹配作者镜像本地库 rel_path。
#
# stat 流转（仅 --execute；dry-run 一个都不动）：
#   打开即 share invalid          -> 6 SHARE_DEAD（终态；作者更新帖会被 collect 重置回 0）
#   计划为空（增量对比后全已覆盖） -> 3 CONSUMED
#   全部 op 转存成功              -> 3 CONSUMED
#   打开/walk 失败（非死链）/部分 op 失败 -> 保持 2，下轮重跑天然重试
#     （重跑会把已成功 op 再转一遍；百度盘目标目录已有同名项时按页面行为处理，
#      现阶段接受重复，与升级前 --ids 手动补跑策略一致）
#
# 流水式逐链接执行（不攒页面）：walk -> 打印计划 -> 立刻执行 -> 关页 -> 下一条。
# 中途挂掉已完成的链接不受影响，--ids 指定剩余重跑。

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_ROOT, "data", "cangku.db")
_LOCAL_DB = os.path.join(_ROOT, "data", "local_library.db")
_REPORT = os.path.join(_ROOT, "data", "consume_report.txt")

# 冒烟集：Solis 新作者整目录（根级 op）/ ink+ 月份目录单元 / AS109 散文件 /
# Erio 多 op + 重抓月精确补齐（月目录内单文件）
SMOKE_IDS = ["225540", "219782", "216571", "222356"]


def load_links(store: PostStore, ids=None, limit=None) -> list[ShareLink]:
  """consume 队列（stat=2）-> ShareLink 列表，新帖在前。

  links_json 里只挑百度项（每帖恰 1 条，post_filter 阶段已保证）；工况内但
  没有百度项的帖子不进队列（存量实测 0 个，防御性跳过）。"""
  out = []
  for p in store.pending_consume():
    links = json.loads(p.links_json or "[]")
    baidu = [l for l in links
             if l.get("pan_type") == "baidu" or "pan.baidu.com" in (l.get("url") or "")]
    if not baidu:
      continue
    l = baidu[0]
    out.append(ShareLink(
        post_url=p.url, post_id=p.url.rstrip("/").split("/")[-1],
        title=p.title, url=l["url"], pwd=l.get("pwd") or None,
        box_title=l.get("box_title") or ""))
  out.sort(key=lambda x: int(x.post_id) if x.post_id.isdigit() else 0, reverse=True)
  if ids:
    want = {str(i) for i in ids}
    out = [x for x in out if x.post_id in want]
  if limit:
    out = out[:limit]
  return out


async def close_quietly(link_page):
  # 执行期 save_executor 从第 2 个 op 起换新页并关掉原页面，这里可能已关过
  try:
    await link_page.page.close()
  except Exception:
    pass


async def main(smoke=False, ids=None, limit=None, execute=False, auto_yes=False):
  target_base = f"/扒/{datetime.date.today():%Y%m%d}"
  print(f"模式: {'真跑（execute）' if execute else 'dry-run（不动 stat）'}；目标根 {target_base}")

  with PostStore(_DB_PATH) as store:
    links = load_links(store, ids=SMOKE_IDS if smoke else ids, limit=limit)
  if not links:
    print("没有可处理的链接（stat=2 且有百度项）")
    return
  local = load_local_months(_LOCAL_DB)
  print(f"本地库作者 {len(local)} 个；分享链接 {len(links)} 个")

  n_consumed = n_dead = n_partial = n_open_fail = 0
  ok_ops = total_ops = 0

  with open(_REPORT, "w", encoding="utf-8") as report:

    def emit(line=""):
      print(line)
      report.write(line + "\n")

    confirmed = auto_yes   # 真跑在第一个非空计划前要一次 yes，后续不再确认
    async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
      for li, link in enumerate(links, 1):
        print(f"\n=== [{li}/{len(links)}] post {link.post_id}  {link.title[:40]}")

        # open + walk 整体重试一次（实测偶发 30s open 超时、walk 中途页面状态丢失）
        tree = None
        link_page = None
        policy = make_policy(local, link.box_title)
        for attempt in (1, 2):
          try:
            link_page = await SharedLinkPage.open(session.context, link.url,
                                                  password=link.pwd)
            tree = await ShareWalker(link_page).walk(policy)
            break
          except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if link_page is not None:
              await link_page.page.close()
              link_page = None
            dead = "share invalid" in str(e)
            if attempt == 1 and not dead:
              logging.warning(f"retry ({link.post_id}): {msg}")
              await asyncio.sleep(3)
            else:
              emit(f"  !! failed, skip: {msg}")
              if dead and execute:
                with PostStore(_DB_PATH) as s:
                  s.mark_share_dead(link.post_url)
                emit(f"  -> 分享已失效，stat 2->6 SHARE_DEAD")
                n_dead += 1
              else:
                n_open_fail += 1   # dry-run 或非死链失败：不动，下轮再试
              break
        if tree is None:
          continue

        ops = await select_ops(link_page, tree, link, local, emit, target_base)
        report.write(format_tree(tree) + "\n")   # 重抓月展开后的最终树
        report.flush()

        if not ops:
          emit("  （无可转存内容：增量对比后全已覆盖，跳过）")
          if execute:
            with PostStore(_DB_PATH) as s:
              s.mark_consumed(link.post_url)
            emit(f"  -> stat 2->3 CONSUMED（全已覆盖）")
            n_consumed += 1
          await close_quietly(link_page)
          await asyncio.sleep(2)
          continue

        emit("\n--- save plan")
        emit(format_plan(ops))

        if not execute:
          await close_quietly(link_page)
          await asyncio.sleep(2)
          continue

        if not confirmed:
          try:
            answer = input(f"\npost {link.post_id} 计划 {len(ops)} 项，目标根 {target_base}，"
                           f"输入 yes 开始执行（后续链接不再确认）: ")
          except EOFError:
            answer = ""
          if answer.strip() != "yes":
            print("未确认，退出（已完成的链接不受影响）")
            return
          confirmed = True

        async def page_factory(link=link):
          # 实测同页"转存成功后再 goto"会确定性挂死，从第 2 个 op 起每个 op 换新页
          return await SharedLinkPage.open(session.context, link.url,
                                           password=link.pwd)

        try:
          results = await execute_save_plan(link_page, ops, page_factory=page_factory)
        except Exception as e:
          logging.error(f"execute crashed ({link.post_id}): {type(e).__name__}: {e}")
          results = []

        emit(format_results(results))
        total_ops += len(ops)
        n_ok = sum(1 for r in results if r.ok)
        ok_ops += n_ok
        if n_ok == len(ops):
          with PostStore(_DB_PATH) as s:
            s.mark_consumed(link.post_url)
          emit(f"  -> stat 2->3 CONSUMED（{n_ok}/{len(ops)} op 全成功）")
          n_consumed += 1
        else:
          emit(f"  -> 部分失败（{n_ok}/{len(ops)}），保持 stat=2 下轮重试")
          n_partial += 1

        await close_quietly(link_page)
        await asyncio.sleep(3)   # 链接间停一下，降低风控风险

    emit(f"\n=== 汇总: 操作 {ok_ops}/{total_ops} 成功；"
         f"帖子 consumed {n_consumed} + share_dead {n_dead} + "
         f"部分失败 {n_partial} + 打开失败 {n_open_fail} / 共 {len(links)}")
    if not execute:
      emit("（dry-run：以上 stat 均未变动）")

  print(f"\n报告已写 {_REPORT}")
  if not auto_yes:
    try:
      input("\ndone, press enter to close browser ")
    except EOFError:
      pass


if __name__ == "__main__":
  ap = argparse.ArgumentParser(description="cangku consume 阶段：百度盘增量转存")
  ap.add_argument("--smoke", action="store_true", help=f"冒烟集 {SMOKE_IDS}")
  ap.add_argument("--ids", default="", help="指定帖子 id，逗号分隔")
  ap.add_argument("--limit", type=int, default=None, help="只处理最新 N 帖")
  ap.add_argument("--execute", action="store_true",
                  help="真跑转存并流转 stat（默认 dry-run 不动 stat）")
  ap.add_argument("--yes", action="store_true", help="跳过人工确认（自动化场景）")
  a = ap.parse_args()
  asyncio.run(main(smoke=a.smoke,
                   ids=[x for x in a.ids.split(",") if x] or None,
                   limit=a.limit, execute=a.execute, auto_yes=a.yes))
