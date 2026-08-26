
"""eroscripts 链接级状态的人工介入渠道（EroLink 表读写）。

  python scripts/ero_links.py counts                     # dl_status 汇总
  python scripts/ero_links.py list --status manual       # 清单（--status 可多次；不传=全部非终态）
  python scripts/ero_links.py set <url> --status downloaded --path <相对路径> --size <字节> --note "..."
      # manual/exhausted 处理完改终态；改回 pending 会清零重试计数重走自动流程
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.sites.eroscripts.store import (
    DL_ALL, DL_FINAL, DL_MANUAL, DL_EXHAUSTED, TopicStore,
)
from scrape_all.storage.models import EroLink

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_ROOT, "data", "eroscripts.db")


def fmt_size(n):
  return f"{n / 1024 / 1024:.1f}MB" if n and n >= 1024 * 1024 else f"{n}B" if n else "-"


def cmd_counts(store):
  counts = store.link_status_counts()
  total = sum(counts.values())
  print(f"EroLink 共 {total} 行，dl_status 分布：")
  for status in sorted(counts):
    mark = "终态" if status in DL_FINAL else "（在途）"
    print(f"  {status:12s} {counts[status]:5d}  {mark}")


def cmd_list(store, statuses):
  # 全量拉取后内存过滤，表只有几千行，够用
  rows = store.db.QueryRecords(EroLink)
  hits = [r for r in rows if not statuses or r.dl_status in statuses]
  print(f"{len(hits)} / {len(rows)} 行" + (f"（筛选 {sorted(statuses)}）" if statuses else "（全部）"))
  for r in hits:
    print(f"  [{r.dl_status:10s}] {r.kind:6s} {r.host:28s} probe={r.probe_status:10s} "
          f"retries={r.probe_retries}/{r.dl_retries} topic={r.first_topic_id}")
    print(f"      {r.url[:120]}")
    if r.dl_note:
      print(f"      note: {r.dl_note}")


def cmd_set(store, url, status, path, size, note):
  store.set_link_status(url, status, path=path, size=size, note=note)
  row = store._require_link(url)
  print(f"已更新 {url}")
  print(f"  dl_status={row.dl_status} path={row.dl_path or '-'} "
        f"size={fmt_size(row.dl_size)} note={row.dl_note or '-'}")
  hint = ""
  if status == DL_MANUAL or status == DL_EXHAUSTED:
    hint = "（该状态为等待/放弃盘点，处理完成后记得 set 成终态）"
  elif status not in DL_FINAL:
    hint = "（已重置回自动流程，下轮编排会重新处理）"
  if hint:
    print(f"  {hint}")


def main():
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description="EroLink 人工介入渠道")
  sub = ap.add_subparsers(dest="cmd", required=True)

  sub.add_parser("counts", help="dl_status 汇总")

  p_list = sub.add_parser("list", help="链接清单")
  p_list.add_argument("--status", action="append",
                      help=f"筛选 dl_status（可多次，可选 {sorted(DL_ALL)}）；不传=全部")

  p_set = sub.add_parser("set", help="人工改链接状态")
  p_set.add_argument("url")
  p_set.add_argument("--status", required=True, choices=sorted(DL_ALL))
  p_set.add_argument("--path", default="", help="落盘相对路径（不传不动）")
  p_set.add_argument("--size", type=int, default=0, help="字节数（不传不动）")
  p_set.add_argument("--note", default="", help="备注（不传不动）")

  args = ap.parse_args()
  with TopicStore(_DB_PATH) as store:
    if args.cmd == "counts":
      cmd_counts(store)
    elif args.cmd == "list":
      cmd_list(store, set(args.status or []))
    elif args.cmd == "set":
      cmd_set(store, args.url, args.status, args.path, args.size, args.note)


if __name__ == "__main__":
  main()
