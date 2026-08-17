
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
import logging
logging.basicConfig(
  level=logging.NOTSET,
  format="[%(asctime)s] %(message)s",
)

from scrape_all.local_library.move import build_plan, execute_plan, print_plan
from scrape_all.local_library.scan import scan
from scrape_all.local_library.store import LibraryStore
from config import LOCAL_LIBRARY_ROOT, LOCAL_LIBRARY_YEJIANG_DIR

# local_library 入口：NAS 库状态镜像 + yejiang 目录归整
#   scan            扫描 [4]confirmed 下 yejiang 夹 -> data/local_library.db
#                   （可解析的入库；工况外的只报告，人工处理）
#   move            默认 dry-run 打印搬运计划；--confirm 交互确认后真搬：
#                   "作者名 {YY.MM} [yejiang]" -> [yejiang]/作者名/（同卷 rename）
# 搬运后文件夹名不再带日期，"上一次fetch最后时间"由库内 folder_date 维护。
# 目标目录名 [yejiang] 带方括号：不匹配顶层命名规范，根扫描天然跳过它自己。

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "local_library.db")


def cmd_scan(_args):
  with LibraryStore(_DB_PATH) as store:
    report = scan(LOCAL_LIBRARY_ROOT, store,
                  yejiang_dir=LOCAL_LIBRARY_YEJIANG_DIR)
  print(f"入库: 新 {report['new']} / 刷新 {report['updated']}")
  for method, n in sorted(report["by_method"].items()):
    print(f"  {method}: {n}")
  if report["out_of_scope"]:
    print(f"\n工况外（不入库不搬运，人工处理）: {len(report['out_of_scope'])}")
    for name, reasons in report["out_of_scope"]:
      print(f"  {name}")
      for r in reasons[:3]:
        print(f"    - {r}")
      if len(reasons) > 3:
        print(f"    ...等 {len(reasons)} 条")
  if report["anomalies"]:
    print(f"\n异常（需要人工看）: {len(report['anomalies'])}")
    for a in report["anomalies"]:
      print(f"  {a}")
  if report["warnings"]:
    print(f"\n提示: {len(report['warnings'])}")
    for w in report["warnings"][:10]:
      print(f"  {w}")
    if len(report["warnings"]) > 10:
      print(f"  ...等 {len(report['warnings'])} 条")


def cmd_move(args):
  with LibraryStore(_DB_PATH) as store:
    folders = store.all_folders()
    if not folders:
      print("库是空的，先跑: python scripts/local_library.py scan")
      return
    items = build_plan(LOCAL_LIBRARY_ROOT, LOCAL_LIBRARY_YEJIANG_DIR, folders)
    print_plan(items, LOCAL_LIBRARY_ROOT)
    if not args.confirm:
      print("\ndry-run（未动任何东西）。确认无误后: python scripts/local_library.py move --confirm")
      return
    answer = input(f"\n将真搬 {sum(1 for i in items if i.action == 'move')} 个文件夹，输入 yes 执行: ")
    if answer.strip() != "yes":
      print("未确认，退出")
      return
    result = execute_plan(items, store, LOCAL_LIBRARY_YEJIANG_DIR)
    print(f"\n=== move done: moved={result['moved']} skipped={result['skipped']} failed={len(result['failed'])}")
    for f in result["failed"]:
      print(f"  failed: {f}")


if __name__ == "__main__":
  ap = argparse.ArgumentParser(description="local_library：NAS 库状态镜像 + yejiang 归整")
  sub = ap.add_subparsers(dest="cmd", required=True)
  sub.add_parser("scan", help="扫描 NAS 库根，建库/刷新镜像")
  ap_move = sub.add_parser("move", help="搬运 yejiang 夹到 yejiang/作者名（默认 dry-run）")
  ap_move.add_argument("--confirm", action="store_true",
                       help="真执行（交互再确认一次）")
  args = ap.parse_args()
  {"scan": cmd_scan, "move": cmd_move}[args.cmd](args)
