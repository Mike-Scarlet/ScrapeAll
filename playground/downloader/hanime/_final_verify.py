# 一次性（只读）：终局核验——该站 dl_status 全分布 + 体积合计 + 330402 落盘文件
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
con = sqlite3.connect(os.path.join(ROOT, "data", "eroscripts.db"))
try:
  rows = con.execute(
      "select dl_status, count(*), sum(dl_size) from EroLink "
      "where host='hanime1.me' group by dl_status").fetchall()
  total = 0
  for st, n, s in rows:
    mb = (s or 0) / 1048576
    total += mb
    print(f"{st:<10} {n:>3} 条  {mb:>10.1f}MB")
  print(f"合计 {sum(r[1] for r in rows)} 条  {total:.1f}MB")
finally:
  con.close()
d = r"J:\es_scrape\330402"
for f in sorted(os.listdir(d)):
  p = os.path.join(d, f)
  print(f"{os.path.getsize(p):>12,}B  {f}")
