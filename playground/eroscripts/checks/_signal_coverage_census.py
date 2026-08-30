# 只读：配对兜底信号覆盖率普查（全部盘上 funscript）：
#   ① metadata.duration / video_url / title 填写率
#   ② actions[-1].at 时长可用率
#   ③ 未配对脚本（沿 _pairing_report 的口径重算）里，其所在帖目录的视频数分布
#      —— 单视频帖可走"唯一视频兜底"，多视频帖必须靠时长匹配
# ffprobe 可用性已知（E:\...\ffprobe.EXE），本脚本不调 ffprobe（快），只统计信号存在性。
import json
import os
import re
import sys
import unicodedata
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEST = r"J:\es_scrape"
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".wmv", ".avi", ".mov", ".flv", ".ts", ".m4v", ".mpg"}

total = 0
has_duration = has_last_at = has_video_url = has_title = 0
video_url_samples = []
per_dir = {}  # tid -> (scripts, videos)

for dirpath, _d, files in os.walk(DEST):
    tid = os.path.basename(dirpath)
    scripts = [f for f in files if f.endswith(".funscript")]
    videos = [f for f in files if os.path.splitext(f)[1].lower() in VIDEO_EXTS]
    if scripts or videos:
        per_dir[tid] = (scripts, videos)
    for fn in scripts:
        p = os.path.join(dirpath, fn)
        total += 1
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        md = data.get("metadata") or {}
        acts = data.get("actions") or []
        if md.get("duration"):
            has_duration += 1
        if acts and acts[-1].get("at"):
            has_last_at += 1
        vu = (md.get("video_url") or "").strip()
        if vu:
            has_video_url += 1
            if len(video_url_samples) < 8:
                video_url_samples.append((tid, fn, vu[:80]))
        if (md.get("title") or "").strip():
            has_title += 1

print(f"盘上 funscript 总数: {total}")
print(f"  metadata.duration 非空: {has_duration}")
print(f"  actions[-1].at 可用:   {has_last_at}")
print(f"  metadata.video_url 非空: {has_video_url}")
print(f"  metadata.title 非空:    {has_title}")
for tid, fn, vu in video_url_samples:
    print(f"    {tid}\\{fn[:40]}  ->  {vu}")

# 未配对脚本（exact/axis/fuzzy 同 _pairing_report 口径）所在目录的视频数分布
AXIS = {"pitch", "roll", "twist", "sway", "surge", "yaw", "lurch"}

def norm(s):
    s = unicodedata.normalize("NFKC", s).casefold()
    return "".join(ch for ch in s if ch.isalnum())

unmatched_dir_video_count = Counter()
n_unmatched = 0
for tid, (scripts, videos) in per_dir.items():
    if not videos:
        continue
    vstems = [os.path.splitext(v)[0] for v in videos]
    vnorms = [norm(s) for s in vstems]
    for sf in scripts:
        stem = os.path.splitext(sf)[0]
        base = stem.rsplit(".", 1)[0] if stem.rsplit(".", 1)[-1].lower() in AXIS else stem
        if norm(stem) in vnorms or norm(base) in vnorms or stem in vstems or base in vstems:
            continue
        n_unmatched += 1
        unmatched_dir_video_count[len(videos)] += 1

print(f"\n有视频目录里的未配对脚本: {n_unmatched}")
print("按所在目录视频数分布（1=唯一视频兜底可用）:")
for k in sorted(unmatched_dir_video_count):
    print(f"  {k} 个视频的目录: {unmatched_dir_video_count[k]} 个脚本")
