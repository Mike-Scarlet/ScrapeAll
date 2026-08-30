# 只读：320427 的链接与落盘现状（供人工重下指引）
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEST = r"J:\es_scrape"
db = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'eroscripts.db')}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

row = db.execute("SELECT * FROM EroTopicItem WHERE topic_id=320427").fetchone()
print(f"topic 320427: {row['title']}")
print(f"  created {row['created_at']}  stat={row['stat']}")
for l in json.loads(row["links_json"] or "[]"):
    print(f"  [{l.get('kind')}] {l.get('name','')}  {l['url']}")

print("\nEroLink 行：")
for r in db.execute("SELECT url, host, kind, dl_status, dl_path, dl_size, dl_note FROM EroLink WHERE first_topic_id=320427 OR dl_path LIKE '320427/%'").fetchall():
    print(f"  {r['kind']}/{r['host']}  {r['dl_status']}  {r['dl_path']}  {r['dl_size']:,}B")
    print(f"    url: {r['url']}")
    print(f"    note: {r['dl_note']}")
    p = os.path.join(DEST, r["dl_path"].replace("/", os.sep))
    print(f"    盘上: {'在' if os.path.exists(p) else '缺'}  实际 {os.path.getsize(p):,}B" if os.path.exists(p) else "    盘上: 缺")
