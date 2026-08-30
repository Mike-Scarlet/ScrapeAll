
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.sites.eroscripts.extract import (
    ArchiveExtractor, resolve_target_dir, zip_preview,
)
from scrape_all.sites.eroscripts.store import TopicStore

# extract 阶段入口：J:\es_scrape 上的 zip/rar 解到包同名子目录（EroExtract 落库）。
# 纯本地零流量；包文件保留不删，嵌套档案递归解到不动点（深度上限 3）。
#
#   python scripts/extract_archives.py            # dry-run：计划 + zip 条目清点，不动盘不动库
#   python scripts/extract_archives.py --execute  # 真跑，开工前输 yes
#   python scripts/extract_archives.py --execute --ids=308104,312321
#
# 幂等：done 跳过、failed 重跑续传（逐条目体积比对）；另一 agent 在途新包
# 落盘后重跑本脚本自动增量接上。

DEST_ROOT = r"J:\es_scrape"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_ROOT, "data", "eroscripts.db")
_REPORT = os.path.join(_ROOT, "data", "eroscripts", "extract_report.txt")


def fmt_mb(n: float) -> str:
  return f"{n / 1024 / 1024:.1f}MB" if n >= 1024 * 1024 else f"{n}B"


def describe(a: dict, dest_root: str) -> str:
  ext = os.path.splitext(a["rel"])[1].lower()
  arrow = " -> " + os.path.relpath(
      resolve_target_dir(a["abs"]), dest_root).replace(os.sep, "/") + "/"
  if ext == ".zip":
    pv = zip_preview(a["abs"])
    if pv["err"]:
      return f"  [zip 打不开: {pv['err']}] {a['rel']}  {fmt_mb(a['size'])}{arrow}"
    return (f"  {a['rel']}  {fmt_mb(a['size'])}"
            f"  条目 {pv['entries']}（视频{pv['video']} 脚本{pv['script']}"
            f" 内嵌档案{pv['archive']} 其他{pv['other']} 杂物{pv['junk']}）"
            f"  解压后 {fmt_mb(pv['uncompressed'])}{arrow}")
  if ext == ".rar":
    return f"  {a['rel']}  {fmt_mb(a['size'])}  （rar 条目解时清点）{arrow}"
  return f"  {a['rel']}  {fmt_mb(a['size'])}  （7z 无工具，将记 failed 人工）{arrow}"


def main(a):
  ids = {int(x) for x in a.ids.split(",") if x} or None
  with TopicStore(_DB_PATH) as store, \
      open(_REPORT, "w", encoding="utf-8") as report:
    def emit(line=""):
      print(line)
      report.write(line + "\n")

    ex = ArchiveExtractor(store, DEST_ROOT, emit=emit)
    plan = ex.plan()
    todo = plan["todo"]
    if ids:
      todo = [x for x in todo if x.get("topic_id") in ids]
    print(f"模式: {'真跑（execute）' if a.execute else 'dry-run（不动盘不动库）'}；"
          f"目标根 {DEST_ROOT}")
    emit(f"盘上档案：待解 {len(todo)} / 已 done 跳过 {len(plan['done'])}"
         f" / 无库引用 {len(plan['no_db'])} / 挂起（父未解）{len(plan['deferred'])}")
    for x in plan["no_db"][:10]:
      emit(f"  [无库引用] {x['rel']}  {fmt_mb(x['size'])}")
    for x in plan["deferred"][:10]:
      emit(f"  [挂起] {x['rel']}")

    if not a.execute:
      for x in todo:
        emit(describe(x, DEST_ROOT))
      emit(f"=== dry-run：{len(todo)} 包待解，未动任何东西 ===")
    else:
      if not a.yes:
        todo_mb = sum(x["size"] for x in todo) / 1024 / 1024
        try:
          answer = input(f"\n共 {len(todo)} 包（压缩体积 {todo_mb:.0f}MB），"
                         f"解到各自包名子目录，输入 yes 开始: ")
        except EOFError:
          answer = ""
        if answer.strip() != "yes":
          print("未确认，退出")
          return
      totals = ex.run(topic_ids=ids)
      parts = [f"pass {totals['passes']}", f"解出 {totals['extracted']} 包",
               f"{totals['files']} 文件 +{totals['bytes'] / 1024 ** 3:.2f}GB 新写"]
      if totals["failed"]:
        parts.append(f"失败 {totals['failed']}")
      parts.append(f"done 跳过 {totals['done_skip']}")
      if totals["no_db"]:
        parts.append(f"无库引用 {totals['no_db']}")
      if totals["deferred"]:
        parts.append(f"挂起 {totals['deferred']}")
      emit("=== 汇总: " + "；".join(parts) + " ===")
  print(f"\n报告已写 {_REPORT}")


if __name__ == "__main__":
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(
      description="eroscripts extract 阶段：zip/rar 解到包同名子目录")
  ap.add_argument("--execute", action="store_true", help="真跑（默认 dry-run）")
  ap.add_argument("--yes", action="store_true", help="跳过开工确认")
  ap.add_argument("--ids", default="", help="只处理这些 topic（逗号分隔）")
  main(ap.parse_args())
