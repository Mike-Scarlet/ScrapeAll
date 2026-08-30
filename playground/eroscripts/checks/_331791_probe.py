# 只读：331791 / 332049 的 dl_path='331228' 异常行溯源
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEST = r"J:\es_scrape"
DB = r"F:\Python\ScrapeAll\data\eroscripts.db"

db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

for tid in ("331791", "332049", "331228"):
    t = db.execute("SELECT topic_id, stat, title, links_json FROM EroTopicItem "
                   "WHERE topic_id = ?", (int(tid),)).fetchone()
    print(f"=== topic {tid}  stat={t['stat']}  {t['title'][:60]}")
    for l in json.loads(t["links_json"] or "[]"):
        url = l.get("url", "")
        r = db.execute("SELECT host, kind, dl_status, dl_path, dl_size FROM EroLink "
                       "WHERE url = ?", (url,)).fetchone()
        tag = "无行" if r is None else f"{r['dl_status']:10} {r['host']:20} path={r['dl_path']!r}"
        print(f"    {tag}  {url[:80]}")
    tdir = os.path.join(DEST, tid)
    if os.path.isdir(tdir):
        print("    盘上:", [f for _dp, _dn, fns in os.walk(tdir) for f in fns][:8])
