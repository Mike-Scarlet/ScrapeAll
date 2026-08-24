
"""只读查库：2026-04 至今的 mega 链接量（按 topic 日期过滤）。"""
import json
import os
import sqlite3
from collections import Counter
from urllib.parse import urlparse

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(_ROOT, "data", "eroscripts.db")

con = sqlite3.connect(DB)
print("EroTopicItem 列：")
cols = [r[1] for r in con.execute("pragma table_info(EroTopicItem)")]
print(" ", cols)

# 找日期列
date_col = next((c for c in cols if c in ("created_at", "posted_at", "created", "dt")), None)
print("日期列：", date_col)

rows = con.execute(
    f"select topic_id, {date_col}, links_json, stat from EroTopicItem "
    "where links_json is not null").fetchall()
print(f"总行数 {len(rows)}")

CUT = "2026-04-01"
n_links = 0
n_topics = 0
shapes = Counter()
per_month = Counter()
stat_cnt = Counter()
samples = []
for t_id, dt, blob, stat in rows:
    d = (dt or "")[:10]
    if d < CUT:
        continue
    try:
        arr = json.loads(blob)
    except (ValueError, TypeError):
        continue
    hit = False
    for item in arr:
        u = (item or {}).get("url") or ""
        if urlparse(u).netloc.lower().removeprefix("www.") in ("mega.nz", "mega.link"):
            n_links += 1
            hit = True
            p = urlparse(u)
            kind = "file" if "/file/" in p.path else ("folder" if "/folder/" in p.path else "other:" + p.path)
            shapes[kind] += 1
            per_month[d[:7]] += 1
    if hit:
        n_topics += 1
        stat_cnt[stat] += 1

print(f"\n2026-04-01 之后: mega 链接 {n_links} 条，分布于 {n_topics} 个 topic")
print("file/folder:", dict(shapes))
print("stat 分布:", dict(stat_cnt))
print("按月:")
for m in sorted(per_month):
    print(f"  {m}: {per_month[m]}")
