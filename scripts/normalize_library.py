
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.sites.eroscripts.normalize import DiskCachedProbe, LibraryNormalizer
from scrape_all.sites.eroscripts.store import TopicStore

# normalize 阶段入口：es_scrape（原始库，只读）→ es_norm（归一化库）落位。
# 配对成功的组：媒体+主脚本同 stem 平铺，多轴 <stem>.<axis>.funscript，
# 变体 <topic>/variants/；视频任一边>1500 转 x264 crf20 按 2 的整数次幂
# 对半除（atplayer normalize_media_in_folder 同款），否则直拷。
# 纯本地零流量，源库不动。
#
#   python scripts/normalize_library.py            # dry-run：计划 + 挂起组清单，不动盘不动库
#   python scripts/normalize_library.py --execute  # 真跑，开工前输 yes
#   python scripts/normalize_library.py --execute --ids=307472,311902
#
# 幂等：EroNorm done + 盘上核验跳过；挂起组（缺平凡原始等优先级表/人工
# 裁决）重跑自动再看一遍。未配对的（歧义/死链/付费墙）不进 es_norm，
# 裁决后重跑即补。

SRC_ROOT = r"J:\es_scrape"
DST_ROOT = r"J:\es_norm"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_ROOT, "data", "eroscripts.db")
_REPORT = os.path.join(_ROOT, "data", "eroscripts", "normalize_report.txt")
_PROBE_CACHE = os.path.join(_ROOT, "data", "eroscripts", "_norm_probe_cache.json")


def main(a):
  ids = {int(x) for x in a.ids.split(",") if x} or None
  probe = DiskCachedProbe(_PROBE_CACHE)
  with TopicStore(_DB_PATH) as store, \
      open(_REPORT, "w", encoding="utf-8") as report:
    def emit(line=""):
      print(line)
      report.write(line + "\n")

    nz = LibraryNormalizer(store, SRC_ROOT, DST_ROOT, emit=emit, probe=probe)
    print(f"模式: {'真跑（execute）' if a.execute else 'dry-run（不动盘不动库）'}；"
          f"源 {SRC_ROOT} -> 目标 {DST_ROOT}")
    try:
      if not a.execute:
        totals = nz.run(topic_ids=ids, execute=False)
        emit(f"=== dry-run 汇总: 帖 {totals['topics']}；配对组 {totals['groups']}"
             f"（挂起 {totals['pending_groups']}）；待落 {totals['files']} 文件"
             f"；歧义脚本 {totals['ambiguous']} / 未配 {totals['unmatched']} ===")
      else:
        if not a.yes:
          try:
            answer = input(f"\n源库只读不动，归一化产物写 {DST_ROOT}，"
                           f"输入 yes 开始: ")
          except EOFError:
            answer = ""
          if answer.strip() != "yes":
            print("未确认，退出")
            return
        totals = nz.run(topic_ids=ids, execute=True)
        parts = [f"帖 {totals['topics']}", f"配对组 {totals['groups']}",
                 f"落位 {totals['copied'] + totals['transcoded']}"
                 f"（直拷 {totals['copied']} / 转码 {totals['transcoded']}）",
                 f"done 跳过 {totals['skip']}"]
        if totals["failed"]:
          parts.append(f"失败 {totals['failed']}")
        if totals["pending_groups"]:
          parts.append(f"挂起 {totals['pending_groups']}")
        parts.append(f"歧义 {totals['ambiguous']} / 未配 {totals['unmatched']}")
        emit("=== 汇总: " + "；".join(parts) + " ===")
    finally:
      probe.save()
  print(f"\n报告已写 {_REPORT}")


if __name__ == "__main__":
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(
      description="eroscripts normalize 阶段：es_scrape -> es_norm 归一化落位")
  ap.add_argument("--execute", action="store_true", help="真跑（默认 dry-run）")
  ap.add_argument("--yes", action="store_true", help="跳过开工确认")
  ap.add_argument("--ids", default="", help="只处理这些 topic（逗号分隔）")
  main(ap.parse_args())
