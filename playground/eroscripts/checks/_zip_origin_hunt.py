# 只读：3 个无库行 zip 的来源追查 —— 各 topic 的全部 EroLink 行 + 落盘文件对照
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DB = r"F:\Python\ScrapeAll\data\eroscripts.db"
DEST = r"J:\es_scrape"

db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

for tid in ("326896", "329078", "331305"):
    print(f"=== topic {tid} ===")
    rows = db.execute(
        "SELECT url, host, kind, dl_status, dl_path, dl_size, dl_at FROM EroLink "
        "WHERE dl_path LIKE ? ORDER BY dl_at", (tid + "/%",)).fetchall()
    for r in rows:
        print(f"  {r['host']:22} {r['kind']:6} {r['dl_status']:10} "
              f"{r['dl_path']}  {r['dl_size']}B  {r['dl_at']}")
    tdir = os.path.join(DEST, tid)
    print("  --- 盘上 ---")
    for dirpath, _dn, fns in os.walk(tdir):
        for fn in fns:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, tdir)
            mt = os.path.getmtime(p)
            import time
            print(f"    {os.path.getsize(p):>12}B  {time.strftime('%m-%d %H:%M', time.localtime(mt))}  {rel}")
