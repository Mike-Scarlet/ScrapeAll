# 只读盘点：刚到的流媒体批次（rule34video 等）落了什么 + extract 要不要补跑
# + 配对素材全树分布（解压后的子目录这次一起算）。
#   1) EroLink 近 48h downloaded 行：host/kind 分布、落点 topic、体积
#   2) 盘上档案 vs EroExtract 行：还有没有 todo / no_db（有 = extract 要补跑）
#   3) 全树清点：每 topic 的 funscript / 视频 / 档案计数，视频按"topic根 / 解压子目录"分家
# 库 mode=ro，盘只 walk 不写。
import json
import os
import posixpath
import sqlite3
import sys
import time
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB = os.path.join(ROOT, "data", "eroscripts.db")
DEST = r"J:\es_scrape"
ARCHIVE_EXTS = {".zip", ".rar", ".7z"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".wmv", ".avi", ".mov", ".flv", ".ts", ".m4v", ".mpg", ".mpeg"}
SCRIPT_EXTS = {".funscript", ".lua"}

db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

# ---------- 1) 近期 downloaded 行 ----------
rows = db.execute(
    "SELECT url, host, kind, dl_path, dl_size, dl_at FROM EroLink "
    "WHERE dl_status='downloaded' AND dl_at IS NOT NULL AND dl_at != '' "
    "ORDER BY dl_at DESC"
).fetchall()
max_at = rows[0]["dl_at"] if rows else "-"
print(f"downloaded 行总数 {len(rows)}，最新 dl_at = {max_at}")
cut = (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 48 * 3600)))
recent = [r for r in rows if r["dl_at"] >= cut]
print(f"\n=== 近 48h（>= {cut}）downloaded {len(recent)} 行 ===")
by_host = Counter((r["host"], r["kind"]) for r in recent)
for (h, k), n in by_host.most_common():
    print(f"  {n:3}  {h:24} {k}")
topic_recent = Counter()
bytes_recent = 0
for r in recent:
    head = (r["dl_path"] or "").split("/")[0].split("\\")[0]
    topic_recent[head] += 1
    bytes_recent += r["dl_size"] or 0
print(f"  体积合计 {bytes_recent/1024/1024/1024:.2f}GB；落点 topic 分布：")
for t, n in topic_recent.most_common():
    print(f"    {t}  x{n}")

# ---------- 2) 档案 vs EroExtract（extract 要不要补跑） ----------
ex_rows = {r["archive_path"]: r for r in db.execute(
    "SELECT archive_path, status, files_json FROM EroExtract")}
st = Counter(r["status"] for r in ex_rows.values())
print(f"\n=== EroExtract: {dict(st)} ===")
disk_archives = []
for dirpath, _dn, fns in os.walk(DEST):
    for fn in fns:
        if os.path.splitext(fn)[1].lower() in ARCHIVE_EXTS:
            rel = os.path.relpath(os.path.join(dirpath, fn), DEST).replace(os.sep, "/")
            disk_archives.append(rel)
known = set(ex_rows)
done = {p for p, r in ex_rows.items() if r["status"] == "done"}
todo = [a for a in disk_archives if a not in known]
no_db = []
for a in todo:
    parent = posixpath.dirname(a.lower())
    if parent and "/" not in parent and parent.isdigit():
        no_db.append(a)   # 顶层无库行引用 -> 不会自动跑
print(f"盘上档案 {len(disk_archives)}；无 EroExtract 行 {len(todo)}"
      f"（其中顶层无库引用 {len(no_db)}）")
for a in todo[:15]:
    print(f"  待解: {a}")

# ---------- 3) 全树配对素材分布 ----------
now_files = 0
topic_stat = {}
for dirpath, _dn, fns in os.walk(DEST):
    rel_dir = os.path.relpath(dirpath, DEST)
    if rel_dir == ".":
        continue
    top = rel_dir.split(os.sep)[0]
    if not top.isdigit():
        continue   # 非话题目录（如果有）
    ts = topic_stat.setdefault(top, Counter())
    at_root = os.sep not in rel_dir
    for fn in fns:
        ext = os.path.splitext(fn)[1].lower()
        if ext in VIDEO_EXTS:
            ts["vid_root" if at_root else "vid_sub"] += 1
            ts["vid_bytes"] += os.path.getsize(os.path.join(dirpath, fn))
        elif ext in SCRIPT_EXTS:
            ts["scr_root" if at_root else "scr_sub"] += 1
        elif ext in ARCHIVE_EXTS:
            ts["arch"] += 1
print(f"\n=== 话题目录 {len(topic_stat)} 个，配对素材分布 ===")
tot = Counter()
both = only_s = only_v = neither = 0
for t, c in sorted(topic_stat.items(), key=lambda kv: -kv[1]["vid_bytes"]):
    tot.update(c)
    nv = c["vid_root"] + c["vid_sub"]
    ns = c["scr_root"] + c["scr_sub"]
    if nv and ns:
        both += 1
    elif ns:
        only_s += 1
    elif nv:
        only_v += 1
    else:
        neither += 1
print(f"  funscript: 根 {tot['scr_root']} + 解压子目录 {tot['scr_sub']} = {tot['scr_root']+tot['scr_sub']}")
print(f"  视频:     根 {tot['vid_root']} + 解压子目录 {tot['vid_sub']} = {tot['vid_root']+tot['vid_sub']}"
      f"  共 {tot['vid_bytes']/1024/1024/1024:.1f}GB")
print(f"  档案留存 {tot['arch']}")
print(f"  帖级: 两边都有 {both} / 只有脚本 {only_s} / 只有视频 {only_v} / 都没有 {neither}")
print("\n体积 top15 帖（脚本/视频按根+子目录）:")
for t, c in sorted(topic_stat.items(), key=lambda kv: -kv[1]["vid_bytes"])[:15]:
    print(f"  {t:8} 脚本 {c['scr_root']}+{c['scr_sub']}  视频 {c['vid_root']}+{c['vid_sub']}"
          f"  {c['vid_bytes']/1024/1024:9.1f}MB")

# 新批次帖的素材现状（近48h 落点 topic 的脚本情况）
print("\n=== 新批次帖素材现状 ===")
for t, n in topic_recent.most_common():
    c = topic_stat.get(t, Counter())
    print(f"  {t:8} 本批 {n} 件  脚本 {c['scr_root']+c['scr_sub']}  视频 {c['vid_root']}+{c['vid_sub']}"
          f"  档案 {c['arch']}")
