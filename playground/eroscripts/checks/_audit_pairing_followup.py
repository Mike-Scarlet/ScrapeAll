# 只读追查：① 3 个"归因不明"帖（downloaded 但目录无视频，dl_path 去哪了）
# ② 2 个坏 zip（312321 / 324125）：库怎么记的、盘上多大、是不是截断
# ③ funscript 时长样本：actions[-1].at 能否作为配对信号（抽几对已配上的验证量级）
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEST = r"J:\es_scrape"
db = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'eroscripts.db')}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

print("=== ① 归因不明候选：dl_status=downloaded 且 kind in (media,source) 的行里，")
print("    dl_path 不指向本帖目录、或指向目录/空路径的 ===")
for r in db.execute(
    "SELECT first_topic_id, url, host, kind, dl_path, dl_size, dl_note FROM EroLink "
    "WHERE dl_status='downloaded' AND kind IN ('media','source')"
):
    p = r["dl_path"] or ""
    tid = str(r["first_topic_id"])
    if p == tid or not p.startswith(tid + "\\"):
        print(f"  topic={tid} kind={r['kind']} host={r['host']}")
        print(f"    url={r['url']}")
        print(f"    dl_path={p!r} size={r['dl_size']} note={r['dl_note']}")

print("\n=== ② 坏 zip ===")
for tid, in [("312321",), ("324125",)]:
    d = os.path.join(DEST, tid)
    if os.path.isdir(d):
        for fn in os.listdir(d):
            p = os.path.join(d, fn)
            head = open(p, "rb").read(16)
            print(f"  {tid}\\{fn}  {os.path.getsize(p)}B  头16字节={head[:8].hex()}")
    for r in db.execute("SELECT url, dl_path, dl_size, dl_note FROM EroLink WHERE first_topic_id=?", (tid,)):
        print(f"    db: {dict(r)}")

print("\n=== ③ funscript 时长样本（exact 已配上对子，验证 actions[-1].at 量级可用性） ===")
pairs = [
    ("307119", "[パントン]大神環 Ogami Tamaki.funscript", "[パントン] 大神環 _ Ogami Tamaki.mp4"),
]
for tid, sf, vf in pairs:
    p = os.path.join(DEST, tid, sf)
    if os.path.exists(p):
        data = json.load(open(p, encoding="utf-8"))
        acts = data.get("actions") or []
        print(f"  {tid} {sf}: actions={len(acts)} last_at={acts[-1]['at'] if acts else None}ms"
              f"  keys={list(data.keys())}")

# 再抽 5 个盘上任意 funscript 看时长分布与 metadata 键
import random
random.seed(7)
count = 0
for dirpath, _d, files in os.walk(DEST):
    for fn in files:
        if not fn.endswith(".funscript") or count >= 5:
            continue
        p = os.path.join(dirpath, fn)
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            print(f"  [坏JSON] {p}: {e}")
            count += 1
            continue
        acts = data.get("actions") or []
        print(f"  {os.path.relpath(p, DEST)}: actions={len(acts)} "
              f"last_at={acts[-1]['at'] if acts else '-'}ms keys={sorted(data.keys())[:8]}")
        count += 1
