
import argparse, asyncio, logging, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
import logging
logging.basicConfig(
  level=logging.NOTSET if os.environ.get("DL_DEBUG") else logging.INFO,
  format="[%(asctime)s] %(message)s",
)

from scrape_all.downloader.engine import DownloadEngine
from scrape_all.sites.eroscripts import consume
from scrape_all.sites.eroscripts.store import DL_FINAL, TopicStore
from scrape_all.storage.models import EroLink
from config import DOWNLOADER_PROXY_SERVER

# consume 阶段入口：eroscripts stat=2 帖子的链接 probe->download 同 phase 流水。
# 帖子按 created_at 升序跑（最旧先吃），guard 之后的存量跑完会把 guard 往后退。
#
#   python scripts/consume_links.py                     # dry-run：只懒登记+打印待处理，不开浏览器
#   python scripts/consume_links.py --execute           # 真跑，开工前输 yes
#   python scripts/consume_links.py --smoke             # 最旧 3 帖冒烟
#   python scripts/consume_links.py --limit=5           # 只吃最旧 5 帖
#   python scripts/consume_links.py --ids=123,456
#   python scripts/consume_links.py --since 2026-03-01  # 临时往后退 guard
#   python scripts/consume_links.py finalize            # 零流量扫尾：全终态帖推 3
#
# 逐链接流水（不攒页面）：probe 判活立刻 download -> 落库 -> 下一帖。
# 中途挂掉已完成的不受影响，重跑从最旧未完成帖继续；unknown/failed 留在
# 重试窗口内下一 pass 再试（共 2 次尝试，耗尽转 exhausted）。
# 人工处理 manual 清单（scripts/ero_links.py set）后跑 finalize 收口。

SINCE = "2026-04-01"     # 时间 guard：往后退就改这里
DEST_ROOT = r"J:\es_scrape"
SMOKE_LIMIT = 3
DEFAULT_CONCURRENCY = 3  # 并发 worker 数（engine 全局闸同步放行）

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_ROOT, "data", "eroscripts.db")
_REPORT = os.path.join(_ROOT, "data", "eroscripts", "consume_report.txt")


def summary_line(totals: dict, execute: bool) -> str:
  parts = [f"帖子 {totals['consumed']}/{totals['topics']} 收口"]
  if totals["registered"]:
    parts.append(f"登记 {totals['registered']}")
  parts.append(f"跳过终态 {totals['skip']}")
  if execute:
    parts += [f"probe 截住 {totals['probe']}", f"download {totals['download']}",
              f"异常 {totals['error']}"]
  else:
    parts.append(f"待处理 {totals['todo']}")
  return "=== 汇总: " + "；".join(parts) + ("（dry-run：stat 未动）" if not execute else "")


async def main(args):
  with TopicStore(_DB_PATH) as store:
    if args.cmd == "finalize":
      counts = consume.finalize_sweep(store, print)
      print(f"finalize: consumed {counts['consumed']} / pending {counts['pending']}"
            f" / unregistered {counts['unregistered']}")
      return

    limit = SMOKE_LIMIT if args.smoke else args.limit
    topics = consume.select_topics(store, since=args.since,
                                   ids=[x for x in args.ids.split(",") if x] or None,
                                   limit=limit)
    if not topics:
      print(f"没有可消费的帖子（stat=2 且 created_at >= {args.since}）")
      return
    empty_dates = [t for t in store.pending_consume_topics() if not t.created_at]
    if empty_dates:
      print(f"（注意：{len(empty_dates)} 帖 stat=2 但 created_at 为空，guard 内不可见，"
            f"如 topic {empty_dates[0].topic_id}）")

    execute = args.execute
    print(f"模式: {'真跑（execute，并发 %d）' % args.concurrency if execute else 'dry-run（不开浏览器，stat 未动）'}；"
          f"guard {args.since}；目标根 {DEST_ROOT}")
    print(f"选中 {len(topics)} 帖（{topics[0].created_at} ~ {topics[-1].created_at}，"
          f"topic {topics[0].topic_id} ~ {topics[-1].topic_id}）")

    if not execute:
      with open(_REPORT, "w", encoding="utf-8") as report:
        def emit(line=""):
          print(line)
          report.write(line + "\n")
        totals = await consume.run_pass(store, topics, DEST_ROOT, emit)
        emit(summary_line(totals, execute))
      print(f"\n报告已写 {_REPORT}")
      return

    # execute：开工前一次性确认（yes / --yes）
    todo_urls = {l["url"] for t in topics for l in consume.topic_links(t)}
    pending = 0
    for u in todo_urls:
      row = store.db.QueryOne(EroLink, where="url = ?", params=(u,))
      if row is None or row.dl_status not in DL_FINAL:
        pending += 1
    if not args.yes:
      try:
        answer = input(f"共 {len(topics)} 帖、去重后 {pending} 链接待处理，"
                       f"目标根 {DEST_ROOT}，输入 yes 开始: ")
      except EOFError:
        answer = ""
      if answer.strip() != "yes":
        print("未确认，退出")
        return

    need_login = any("discuss.eroscripts.com" in u for u in todo_urls)
    with open(_REPORT, "w", encoding="utf-8") as report:
      def emit(line=""):
        print(line)
        report.write(line + "\n")
      # 恒 stealth（patchright 同 profile 同代理，API 兼容）：该流水含吃 CF
      # 挑战的流媒体源站，普通文件托管在 patchright 下行为一致
      async with DownloadEngine(DOWNLOADER_PROXY_SERVER,
                                args.concurrency, stealth=True) as engine:
        if need_login:
          from scrape_all.sites.eroscripts.login import ErosLogin
          await ErosLogin.GuaranteeErosLogin(engine.context)
        totals = await consume.run_pass(store, topics, DEST_ROOT, emit,
                                        engine=engine, concurrency=args.concurrency)
        emit(summary_line(totals, execute))
        if totals["aborted"]:
          emit(f"!! 连续 {consume.ABORT_AFTER} 条链接异常，本 pass 提前撤；"
               f"已完成不受影响，重跑续吃")
        if not args.yes:
          try:
            input("\ndone, press enter to close browser ")
          except EOFError:
            pass
    print(f"\n报告已写 {_REPORT}")


if __name__ == "__main__":
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description="eroscripts consume 阶段：链接 probe+download 流水")
  ap.add_argument("cmd", nargs="?", default="run", choices=("run", "finalize"))
  ap.add_argument("--smoke", action="store_true", help=f"最旧 {SMOKE_LIMIT} 帖冒烟")
  ap.add_argument("--ids", default="", help="指定 topic id，逗号分隔")
  ap.add_argument("--limit", type=int, default=None, help="只处理最旧 N 帖")
  ap.add_argument("--since", default=SINCE,
                  help=f"帖子时间下界 guard（默认 {SINCE}，往后退传更早）")
  ap.add_argument("--execute", action="store_true", help="真跑（默认 dry-run）")
  ap.add_argument("--yes", action="store_true", help="跳过开工确认")
  ap.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                  help=f"并发 worker 数（默认 {DEFAULT_CONCURRENCY}；1=串行）")
  a = ap.parse_args()
  asyncio.run(main(a))
