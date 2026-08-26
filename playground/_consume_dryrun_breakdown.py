
"""只读：dry-run 登记后的 EroLink 状态 × host 分布报数。"""
import os
import sqlite3
from collections import Counter

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
con = sqlite3.connect(os.path.join(_ROOT, "data", "eroscripts.db"))

print("== EroLink 全表 dl_status ==")
for st, n in con.execute("select dl_status, count(*) from EroLink group by 1 order by 2 desc"):
    print(f"  {st:10} {n}")

print("\n== pending 待处理（probe+download 队列）按 host ==")
rows = con.execute("select host, kind, count(*) from EroLink "
                   "where dl_status='pending' group by 1,2 order by 3 desc").fetchall()
host_tot = Counter()
for host, kind, n in rows:
    host_tot[host] += n
for host, n in host_tot.most_common():
    kinds = " ".join(f"{k}×{m}" for h, k, m in rows if h == host)
    print(f"  {host:28} {n:4}  ({kinds})")

print("\n== manual（无 adapter 等人工）按 host ==")
for host, n in con.execute("select host, count(*) from EroLink "
                           "where dl_status='manual' group by 1 order by 2 desc"):
    print(f"  {host:28} {n}")

print("\n== stat=2 帖 created_at 为空的（guard 内不可见）==")
print(" ", con.execute("select count(*) from EroTopicItem where stat=2 "
                       "and (created_at is null or created_at='')").fetchone()[0])
con.close()
