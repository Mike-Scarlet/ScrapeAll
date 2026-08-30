# 只读：323371 media downloaded 但树内无视频 —— 链接行 + 盘上实况
import json
import os
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEST = r"J:\es_scrape"
DB = r"F:\Python\ScrapeAll\data\eroscripts.db"

db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

t = db.execute("SELECT topic_id, stat, title, links_json FROM EroTopicItem "
               "WHERE topic_id = 323371").fetchone()
print(f"topic 323371  stat={t['stat']}  {t['title'][:70]}")
for l in json.loads(t["links_json"] or "[]"):
    url = l.get("url", "")
    r = db.execute("SELECT host, kind, dl_status, dl_path, dl_size, dl_at FROM EroLink "
                   "WHERE url = ?", (url,)).fetchone()
    if r is None:
        print(f"  [无行] {url[:90]}")
    else:
        print(f"  [{r['dl_status']:10}] {r['host']:22} path={r['dl_path']!r} "
              f"{r['dl_size']}B at={r['dl_at']}")

tdir = os.path.join(DEST, "323371")
print("--- 盘上 ---")
for dirpath, _dn, fns in os.walk(tdir):
    for fn in fns:
        p = os.path.join(dirpath, fn)
        print(f"  {os.path.getsize(p):>12}B  {time.strftime('%m-%d %H:%M', time.localtime(os.path.getmtime(p)))}"
              f"  {os.path.relpath(p, tdir)}")
