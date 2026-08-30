# 只读实验 1：EroLink downloaded 行 vs J:\es_scrape 实盘对账。
#   - 逐行验 dl_path 存在性 + dl_size 一致性（缺失/体积不符/未知体积）
#   - 重复 dl_path（两行指同一文件）/ 跨行覆盖嫌疑
#   - 实盘 orphan：不在任何 downloaded 行 dl_path 里的文件
#   - 另一 agent 在并发下载：mtime 30 分钟内的单列"在途"不算异常
# 库只读打开（mode=ro），盘只 walk 不写。
import os
import sys
import time
from collections import Counter, defaultdict

import sqlite3

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB = os.path.join(ROOT, "data", "eroscripts.db")
DEST = r"J:\es_scrape"
NOW = time.time()
IN_FLIGHT_S = 30 * 60

db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

rows = db.execute(
    "SELECT url, host, kind, dl_path, dl_size, dl_at FROM EroLink "
    "WHERE dl_status='downloaded' AND dl_path IS NOT NULL AND dl_path != ''"
).fetchall()
print(f"downloaded 且有 dl_path 的行: {len(rows)}")

# --- 行 -> 实盘 ---
ok = exact = size_diff = missing = size_unknown = 0
diffs, missings, unknowns = [], [], []
path_owner = defaultdict(list)
for r in rows:
    rel = r["dl_path"].replace("/", os.sep)
    abs_p = os.path.join(DEST, rel)
    path_owner[os.path.normcase(rel)].append(r["url"])
    if not os.path.exists(abs_p):
        missing += 1
        missings.append((r["kind"], r["host"], rel, r["dl_size"], r["dl_at"]))
        continue
    actual = os.path.getsize(abs_p)
    if r["dl_size"] is None:
        size_unknown += 1
        unknowns.append((r["kind"], r["host"], rel, actual))
    elif actual != r["dl_size"]:
        size_diff += 1
        diffs.append((r["kind"], r["host"], rel, r["dl_size"], actual))
    else:
        exact += 1
    ok += 1

print(f"实盘在: {ok} / 缺失: {missing} / 体积精确对上: {exact} / 体积不符: {size_diff} / 库无体积: {size_unknown}")

dupes = {p: urls for p, urls in path_owner.items() if len(urls) > 1}
print(f"多行共用同一 dl_path: {len(dupes)}")
for p, urls in list(dupes.items())[:10]:
    print(f"  {p}  x{len(urls)}  {urls}")

if missings:
    print(f"\n=== 缺失 {missing} 明细（前 20） ===")
    for kind, host, rel, size, at in missings[:20]:
        print(f"  {kind:7} {host:22} {rel}  库记 {size}B  dl_at={at}")
if diffs:
    print(f"\n=== 体积不符 {size_diff} 明细（前 20） ===")
    for kind, host, rel, s_db, s_real in diffs[:20]:
        print(f"  {kind:7} {host:22} {rel}  库 {s_db}B vs 盘 {s_real}B (Δ{s_real - s_db:+d})")
if unknowns:
    print(f"\n=== 库无体积 {size_unknown} 明细（前 10） ===")
    for kind, host, rel, actual in unknowns[:10]:
        print(f"  {kind:7} {host:22} {rel}  盘 {actual}B")

# --- 实盘 -> 行（orphan）---
referenced = set(path_owner)  # normcase rel paths
orphans, in_flight = [], []
walk_files = 0
walk_bytes = 0
for dirpath, _dirnames, filenames in os.walk(DEST):
    for fn in filenames:
        p = os.path.join(dirpath, fn)
        rel = os.path.normcase(os.path.relpath(p, DEST))
        walk_files += 1
        try:
            sz = os.path.getsize(p)
            mt = os.path.getmtime(p)
        except OSError:
            continue
        walk_bytes += sz
        if rel not in referenced:
            (in_flight if NOW - mt < IN_FLIGHT_S else orphans).append((rel, sz))

print(f"\n=== 实盘文件 {walk_files} 个 / {walk_bytes/1024/1024/1024:.2f}GB；未引用: {len(orphans)} 常态 + {len(in_flight)} 近30分钟(在途) ===")
by_ext = Counter(os.path.splitext(rel)[1].lower() for rel, _ in orphans)
print("orphan 扩展名分布:", dict(by_ext))
for rel, sz in sorted(orphans, key=lambda x: -x[1])[:25]:
    print(f"  {sz/1024/1024:10.1f}MB  {rel}")
