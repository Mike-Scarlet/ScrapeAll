
"""只读：并发版启用前的队列余量报数。"""
import os
import sqlite3
from collections import Counter

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
con = sqlite3.connect(os.path.join(_ROOT, "data", "eroscripts.db"))

print("stat:", dict(con.execute("select stat, count(*) from EroTopicItem group by 1")))
print("EroLink:", dict(con.execute("select dl_status, count(*) from EroLink group by 1")))
print("\nguard(2026-04-01) 内 stat=2 帖:", con.execute(
    "select count(*) from EroTopicItem where stat=2 and created_at >= '2026-04-01'"
).fetchone()[0])
print("guard 内待处理链接（pending 行）按 host:")
rows = con.execute(
    "select host, kind, count(*) from EroLink where dl_status='pending' "
    "group by 1,2 order by 3 desc").fetchall()
for host, kind, n in rows:
    print(f"  {host:28} {n:4}  ({kind})")
con.close()
