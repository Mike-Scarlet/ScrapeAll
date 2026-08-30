# 只读续：3 帖的 links_json -> EroLink 全行对照（不看 dl_path 前缀，看 url 本身）
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DB = r"F:\Python\ScrapeAll\data\eroscripts.db"

db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

for tid in ("326896", "329078", "331305"):
    print(f"=== topic {tid} ===")
    t = db.execute("SELECT topic_id, stat, title, links_json FROM EroTopicItem "
                   "WHERE topic_id = ?", (int(tid),)).fetchone()
    if not t:
        print("  无 EroTopicItem 行!")
        continue
    print(f"  stat={t['stat']}  {t['title'][:60]}")
    try:
        links = json.loads(t["links_json"] or "[]")
    except ValueError:
        links = []
    for l in links:
        url = (l or {}).get("url", "")
        if not url:
            continue
        r = db.execute("SELECT host, kind, dl_status, dl_path, dl_size, dl_at "
                       "FROM EroLink WHERE url = ?", (url,)).fetchone()
        if r is None:
            print(f"  [无行] {url[:90]}")
        else:
            print(f"  [{r['dl_status']:10}] {r['host']:22} dl_path={r['dl_path']!r} "
                  f"{r['dl_size']}B at={r['dl_at']}")
