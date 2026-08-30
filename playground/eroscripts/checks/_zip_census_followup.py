# 只读实验：zip 普查跟进——混合包自配对验证 + other 条目构成 + 内部目录结构 + 嵌套包定位
import os
import sqlite3
import sys
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEST = r"J:\es_scrape"
VIDEO_EXT = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".m4v", ".mpg", ".mpeg", ".ts", ".flv"}
SCRIPT_EXT = {".funscript", ".lua"}

zips = []
for dirpath, _dn, filenames in os.walk(DEST):
    for fn in filenames:
        if fn.lower().endswith(".zip"):
            zips.append(os.path.join(dirpath, fn))
zips.sort()

selfpair_full = selfpair_dir = video_noscript = mixed = 0
other_ext = Counter()
nested_list = []
depth_hist = Counter()
flat_pkgs = nested_pkgs = 0
detail_selfpair_miss = []

for p in zips:
    with zipfile.ZipFile(p) as z:
        vids, scripts, others = [], [], []
        max_depth = 0
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            base = name.rsplit("/", 1)[-1]
            ext = os.path.splitext(base)[1].lower()
            depth = name.count("/")
            max_depth = max(max_depth, depth)
            if ext in VIDEO_EXT:
                vids.append(name)
            elif ext in SCRIPT_EXT:
                scripts.append(name)
            elif ext in {".zip", ".rar", ".7z"}:
                nested_list.append(f"{os.path.relpath(p, DEST)} :: {name}")
                others.append(name)
            else:
                other_ext[ext] += 1
                others.append(name)
        if max_depth == 0:
            flat_pkgs += 1
        else:
            nested_pkgs += 1
            depth_hist[max_depth] += 1
        if vids and scripts:
            mixed += 1
            # 自配对：脚本 stem 是否有同名视频（含轴变体后缀 pitch/surge/roll/twist/sway/yaw/lurch）
            vmap = {}
            for v in vids:
                stem = os.path.splitext(os.path.basename(v))[0]
                vmap.setdefault(stem, v)
            hit = 0
            for s in scripts:
                stem = os.path.splitext(os.path.basename(s))[0]
                if stem in vmap:
                    hit += 1
            if hit == len(scripts):
                selfpair_full += 1
            elif hit:
                selfpair_dir += 1
            else:
                detail_selfpair_miss.append(os.path.relpath(p, DEST))
        elif vids:
            video_noscript += 1

print(f"混合包 {mixed} 个：脚本全部同 stem 自配对 {selfpair_full} / 部分命中 {selfpair_dir} / 全不中 {mixed - selfpair_full - selfpair_dir}")
print(f"\n纯视频包（解压后要靠外部脚本配）: {video_noscript} 个")
if detail_selfpair_miss:
    print("全不中示例（前 10）：")
    for rel in detail_selfpair_miss[:10]:
        print(f"  {rel}")

print(f"\nother 条目扩展名分布: {dict(other_ext)}")
print(f"内部结构：纯平铺（无目录）{flat_pkgs} / 带目录 {nested_pkgs}（最大深度分布 {dict(depth_hist)}）")
print(f"嵌套档案 {len(nested_list)} 个：")
for x in nested_list[:10]:
    print(f"  {x}")
