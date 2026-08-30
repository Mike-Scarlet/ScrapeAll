# 只读实验 2：funscript ↔ 视频配对报告（不改名、不解压、不写库）。
# 以 J:\es_scrape\<topic_id>\ 目录为单位（播放器视角），配对层级：
#   exact    : stem 逐字符相等（Windows normcase）
#   variant  : 脚本 stem == 视频 stem + "." + 多轴后缀（pitch/surge/...），再走 exact/fuzzy
#   fuzzy    : NFKC + casefold + 剔除所有非字母数字后相等（对齐 307119 实例）
# zip 只读中央目录窥内含条目（video/funscript 计数），不解压。
# SCRIPT_NO_VIDEO 归因走 links_json -> EroLink：media/source 链接的 dl_status 说了算
# （dead / 在 zip 未解压 / 文件在共享 URL 的 first_topic_id 目录 / 真没配上）。
import json
import os
import re
import sqlite3
import sys
import unicodedata
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB = os.path.join(ROOT, "data", "eroscripts.db")
DEST = r"J:\es_scrape"

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".wmv", ".avi", ".mov", ".flv", ".ts", ".m4v", ".mpg"}
SCRIPT_EXTS = {".funscript"}
ARCHIVE_EXTS = {".zip", ".rar"}
AXIS_SUFFIXES = {"pitch", "roll", "twist", "sway", "surge", "yaw", "lurch"}

db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row


def norm_stem(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    return re.sub(r"[^0-9a-z\ue000-\uffff]+", "", s)
    # 假名/汉字落在 \ue000-\uffff 附近之外（CJK 主区 < \u9fff），见下


def norm_stem2(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    return "".join(ch for ch in s if ch.isalnum())


def strip_axis(stem: str):
    """剥一层多轴后缀：'name.pitch' -> ('name', 'pitch')；无后缀 -> (stem, None)"""
    i = stem.rfind(".")
    if i > 0 and stem[i + 1:].lower() in AXIS_SUFFIXES:
        return stem[:i], stem[i + 1:].lower()
    return stem, None


# --- 库：url -> 行（共享 URL 的真实落点）、topic_id -> links_json ---
link_rows = {r["url"]: r for r in db.execute(
    "SELECT url, kind, dl_status, dl_path, dl_size FROM EroLink")}
topic_links = {}
for r in db.execute("SELECT topic_id, links_json, title FROM EroTopicItem"):
    try:
        arr = json.loads(r["links_json"] or "[]")
    except ValueError:
        arr = []
    topic_links[r["topic_id"]] = [l for l in arr if (l or {}).get("url")]

states = Counter()
script_tier_total = Counter()
fuzzy_only, no_video_detail, zip_topics = [], [], []
video_no_script = []

dirs = sorted(os.listdir(DEST))
for tid in dirs:
    tdir = os.path.join(DEST, tid)
    if not os.path.isdir(tdir):
        continue
    scripts, videos, zips = [], [], []
    for fn in os.listdir(tdir):
        ext = os.path.splitext(fn)[1].lower()
        if ext in SCRIPT_EXTS:
            scripts.append(fn)
        elif ext in VIDEO_EXTS:
            videos.append(fn)
        elif ext in ARCHIVE_EXTS:
            zips.append(fn)

    # zip 内窥（只读中央目录）
    zip_v, zip_s, zip_bad = 0, 0, 0
    for zn in zips:
        try:
            with zipfile.ZipFile(os.path.join(tdir, zn)) as zf:
                for info in zf.infolist():
                    e = os.path.splitext(info.filename)[1].lower()
                    if e in VIDEO_EXTS:
                        zip_v += 1
                    elif e in SCRIPT_EXTS:
                        zip_s += 1
        except Exception:
            zip_bad += 1
    if zips:
        zip_topics.append((tid, len(zips), zip_v, zip_s, zip_bad))

    def match(script_stem, video_stems):
        """返回 (tier, video) tier: exact/variant/fuzzy/vfuzzy/None"""
        ns = norm_stem2(script_stem)
        for vs in video_stems:
            if os.path.normcase(script_stem) == os.path.normcase(vs):
                return "exact", vs
        for vs in video_stems:
            if ns == norm_stem2(vs):
                return "fuzzy", vs
        return None, None

    if not videos:
        # 无视频：全部脚本无配对可言，直接归因（看 links_json -> EroLink 状态）
        links = topic_links.get(int(tid), [])
        ms = [link_rows.get(l["url"]) for l in links
              if link_rows.get(l["url"]) and link_rows[l["url"]]["kind"] in ("media", "source")]
        dl = [r for r in ms if r["dl_status"] == "downloaded"]
        dead = [r for r in ms if r["dl_status"] == "dead"]
        other = [r for r in ms if r["dl_status"] not in ("downloaded", "dead")]
        if not ms:
            states["SCRIPT_ONLY_TOPIC(无media/source链接)"] += 1
        elif not scripts:
            states["EMPTY_OR_VIDEO_IN_ZIP_ONLY"] += 1
        elif zip_v:
            states["SCRIPT_NO_VIDEO__媒体在zip未解压"] += 1
            no_video_detail.append((tid, "zip内含视频未解压", f"zip{len(zips)}个 内视频{zip_v}", scripts[:3]))
        elif dead and not dl:
            states["SCRIPT_NO_VIDEO__media全死链"] += 1
            no_video_detail.append((tid, "media死链", f"dead {len(dead)}", scripts[:3]))
        elif dl:
            # 下载了但本目录没有视频文件：共享 URL 落在别的目录？
            elsewhere = [r["dl_path"] for r in dl
                         if r["dl_path"] and not r["dl_path"].startswith(tid + os.sep)]
            if elsewhere:
                states["SCRIPT_NO_VIDEO__文件在共享URL他帖目录"] += 1
                no_video_detail.append((tid, "共享URL落他目录", "; ".join(elsewhere[:2]), scripts[:3]))
            else:
                states["SCRIPT_NO_VIDEO__归因不明(查)"] += 1
                no_video_detail.append((tid, "downloaded但目录无视频", f"paths {[r['dl_path'] for r in dl][:2]}", scripts[:3]))
        else:
            states[f"SCRIPT_NO_VIDEO__media态{Counter(r['dl_status'] for r in ms)}"] += 1
            no_video_detail.append((tid, "media非downloaded非dead", str(Counter(r['dl_status'] for r in ms)), scripts[:3]))
        continue

    # 有视频：脚本逐个配
    video_stems = [os.path.splitext(v)[0] for v in videos]
    tiers = Counter()
    unmatched_scripts = []
    fuzzy_pairs = []
    for sf in scripts:
        stem = os.path.splitext(sf)[0]
        base, axis = strip_axis(stem)
        # 脚本 stem 直接对视频 stem；或剥轴后缀后对
        t1, v1 = match(stem, video_stems)
        if t1:
            tiers[t1] += 1
            if t1 == "fuzzy":
                fuzzy_pairs.append((sf, v1))
            continue
        t2, v2 = match(base, video_stems)
        if t2:
            tiers[f"{t2}+variant"] += 1
            if t2 == "fuzzy":
                fuzzy_pairs.append((sf, v2))
            continue
        unmatched_scripts.append(sf)
    script_tier_total.update(tiers)
    script_tier_total["unmatched"] += len(unmatched_scripts)
    if scripts and not unmatched_scripts:
        if tiers.get("exact") or tiers.get("exact+variant"):
            states["OK_全配对(exact)"] += 1
        else:
            states["OK_全配对(仅fuzzy)"] += 1
    elif scripts:
        if tiers.get("exact") or tiers.get("exact+variant"):
            states["PARTIAL_部分配对"] += 1
        elif tiers:
            states["FUZZY_ONLY_仅模糊配对"] += 1
        else:
            states["NONE_全未配对"] += 1
        fuzzy_only.append((tid, dict(tiers), unmatched_scripts[:4], videos[:4], fuzzy_pairs[:4]))
    else:
        states["VIDEO_ONLY_无脚本"] += 1
        video_no_script.append(tid)

print(f"topic 目录: {len(dirs)}")
print("\n=== 帖级配对状态分布 ===")
for k, v in states.most_common():
    print(f"  {v:4}  {k}")

print("\n=== 含 zip 的帖（zip数/内视频/内脚本/坏zip） ===")
for tid, nz, zv, zs, zb in zip_topics:
    print(f"  {tid}  zip={nz} 内视频={zv} 内脚本={zs} 坏={zb}")

print(f"\n=== 脚本级配对分层（全部 funscript 文件） ===")
for k, v in script_tier_total.most_common():
    print(f"  {v:4}  {k}")

print(f"\n=== 未全配对帖明细（NONE/FUZZY/PARTIAL，前 30） ===")
for tid, tiers, unmatched, vids, fpairs in fuzzy_only[:30]:
    print(f"  {tid}  {tiers}")
    print(f"    未配脚本: {unmatched}")
    print(f"    视频: {vids}")
    if fpairs:
        print(f"    fuzzy对子: {fpairs}")

print(f"\n=== SCRIPT_NO_VIDEO 归因明细（前 30） ===")
for tid, why, ev, scripts in no_video_detail[:30]:
    print(f"  {tid}  {why}  {ev}")
    print(f"    脚本: {scripts}")

print(f"\n=== VIDEO_ONLY（有视频无脚本）帖数: {len(video_no_script)} ===")
print(" ", video_no_script[:30])
