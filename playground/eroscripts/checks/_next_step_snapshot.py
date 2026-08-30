"""只读快照：EroLink 状态分布 + stat=2 待消费队列构成，供下一步规划对账。"""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[3] / "data" / "eroscripts.db"
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

print("=== EroLink dl_status ===")
for r in db.execute("SELECT dl_status, COUNT(*) c FROM EroLink GROUP BY dl_status ORDER BY c DESC"):
    print(dict(r))

print("\n=== EroLink probe_status ===")
for r in db.execute("SELECT probe_status, COUNT(*) c FROM EroLink GROUP BY probe_status ORDER BY c DESC"):
    print(dict(r))

print("\n=== kind x dl_status ===")
for r in db.execute("SELECT kind, dl_status, COUNT(*) c FROM EroLink GROUP BY kind, dl_status ORDER BY kind, c DESC"):
    print(f"{r['kind']:10} {str(r['dl_status']):10} {r['c']}")

print("\n=== stat=2 队列按 host 构成（未登记的看 links_json） ===")
for r in db.execute(
    "SELECT host, COUNT(*) c FROM EroLink WHERE first_topic_id IN (SELECT topic_id FROM EroTopicItem WHERE stat=2) GROUP BY host ORDER BY c DESC LIMIT 20"
):
    print(dict(r))

print("\n=== stat=2 队列按 created_at 年月分布 ===")
for r in db.execute(
    "SELECT substr(created_at,1,7) ym, COUNT(*) c FROM EroTopicItem WHERE stat=2 GROUP BY ym ORDER BY ym"
):
    print(dict(r))

print("\n=== dl_status=manual 明细（人工挂账） ===")
for r in db.execute("SELECT url, host, kind FROM EroLink WHERE dl_status='manual' LIMIT 30"):
    print(dict(r))

print("\n=== dl_status=exhausted 明细（自动放弃） ===")
for r in db.execute("SELECT url, host, kind, probe_status FROM EroLink WHERE dl_status='exhausted' LIMIT 30"):
    print(dict(r))
