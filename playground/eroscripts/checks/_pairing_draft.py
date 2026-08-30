# 只读实验 3（v2）：funscript ↔ 媒体配对决策表草案（解压后全树 + 流媒体新版）。
# 不改名、不写库、不动盘（ffprobe 只读探时长，缓存落 data/）。
#
# v2 升级（v1 首跑 138 ambiguous / 101 未配的教训）：
#   - 内容身份去重：脚本与候选媒体都按 (basename, size) 归并成逻辑对象，
#     root/解压子目录/嵌套包里的同名同体积副本算一份（镜像数入报告）
#   - 画质档：同名不同体积的候选（73MB vs 256MB 双档）时长分不开（内容同时长），
#     默认配大件、conf B、进人工复核清单；不同名多候选仍走时长挑/ambiguous
#   - 候选池扩容：帖自身 EroLink downloaded media/source 的 dl_path 指到的文件
#     （共享 URL 落他帖目录的 13 案由此入池，标"跨帖"）
#   - 音频次级目标：音声作品包（wav/srt 无视频，323371 案）——视频层全空后
#     对 .wav/.mp3 跑同样分层，method 带 audio: 前缀
# 匹配分层（先到先得）：
#   exact / axis+exact / fuzzy / axis+fuzzy / tagstrip / axis+tagstrip / contain
#   / dur（名字层全空，ffprobe ±2s 唯一命中）/ single-video（帖内唯一媒体兜底）
# 时长另作验证器：|Δ|<=2s 标 dur✓；2~10s 标 Δ；>10s 标 dur✗（保留配对但降置信）。
# 库只读；全表写 data/eroscripts/pairing_draft.txt。
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import unicodedata
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB = os.path.join(ROOT, "data", "eroscripts.db")
DEST = r"J:\es_scrape"
FFPROBE = r"E:\Program Files\ffmpeg\bin\ffprobe.EXE"
DUR_CACHE = os.path.join(ROOT, "data", "eroscripts", "_pairing_dur_cache.json")
REPORT = os.path.join(ROOT, "data", "eroscripts", "pairing_draft.txt")

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".wmv", ".avi", ".mov", ".flv", ".ts",
              ".m4v", ".mpg", ".mpeg"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus"}
SCRIPT_EXTS = {".funscript", ".lua"}
AXIS_SUFFIXES = {"pitch", "roll", "twist", "sway", "surge", "yaw", "lurch"}
QUALITY_RE = re.compile(r"[ _\-.]*(2160p|1440p|1080p|720p|480p|360p|4k|60fps|30fps)$", re.I)
TAG_RE = re.compile(r"\s*[\(\[][^\(\)\[\]]*[\)\]]\s*$")
DUR_TIGHT = 2.0
DUR_WEAK = 10.0
CONTAIN_MIN = 6

db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    return "".join(ch for ch in s if ch.isalnum())


def strip_axis(stem: str):
    i = stem.rfind(".")
    if i > 0 and stem[i + 1:].lower() in AXIS_SUFFIXES:
        return stem[:i], stem[i + 1:].lower()
    return stem, None


def strip_quality(stem: str) -> str:
    prev = None
    while prev != stem:
        prev, stem = stem, QUALITY_RE.sub("", stem)
    return stem


def strip_tag(stem: str) -> str:
    return TAG_RE.sub("", stem)


# ---------- 溯源 ----------
prov: dict[str, str] = {}
for r in db.execute("SELECT host, kind, dl_path FROM EroLink "
                    "WHERE dl_status='downloaded' AND dl_path != ''"):
    prov.setdefault(os.path.normcase(r["dl_path"].replace("\\", "/")),
                    f"{r['host'].split('.')[0]}:{r['kind']}")
for r in db.execute("SELECT archive_path, files_json FROM EroExtract WHERE status='done'"):
    pkg = os.path.splitext(os.path.basename(r["archive_path"]))[0][:40]
    try:
        for f in json.loads(r["files_json"] or "[]"):
            prov.setdefault(os.path.normcase(f["path"]), f"pkg:{pkg}")
    except ValueError:
        pass

# ---------- 时长 ----------
_dur_cache: dict[str, str] = {}
if os.path.exists(DUR_CACHE):
    try:
        _dur_cache = json.load(open(DUR_CACHE, encoding="utf-8"))
    except (ValueError, OSError):
        _dur_cache = {}


def media_dur(rel: str, abspath: str):
    try:
        st = os.stat(abspath)
        key = f"{rel}|{st.st_size}|{int(st.st_mtime)}"
        if key in _dur_cache:
            return float(_dur_cache[key]) if _dur_cache[key] != "" else None
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", abspath],
            capture_output=True, text=True, timeout=15)
        val = r.stdout.strip()
        dur = None
        try:
            dur = float(val)
        except ValueError:
            pass
        _dur_cache[key] = "" if dur is None else val
        return dur
    except (OSError, subprocess.SubprocessError):
        return None


def script_dur(abspath: str):
    if abspath.lower().endswith(".lua"):
        return None
    try:
        acts = json.load(open(abspath, encoding="utf-8", errors="replace")).get("actions") or []
        return acts[-1]["at"] / 1000 if acts else None
    except (OSError, ValueError, KeyError, IndexError):
        return None


# ---------- 帖链接态 ----------
topic_links = {}
for r in db.execute("SELECT topic_id, links_json FROM EroTopicItem"):
    try:
        topic_links[r["topic_id"]] = [l.get("url") for l in json.loads(r["links_json"] or "[]") if l.get("url")]
    except (ValueError, AttributeError, TypeError):
        topic_links[r["topic_id"]] = []
link_by_url = {r["url"]: r for r in db.execute(
    "SELECT url, kind, dl_status, dl_path FROM EroLink")}


def media_state(tid: int) -> str:
    urls = topic_links.get(tid, [])
    rows = [link_by_url[u] for u in urls if u in link_by_url
            and link_by_url[u]["kind"] in ("media", "source")]
    if not rows:
        return "无media/source链接"
    dl = [r for r in rows if r["dl_status"] == "downloaded"]
    dead = [r for r in rows if r["dl_status"] == "dead"]
    if dl:
        elsewhere = [r["dl_path"] for r in dl
                     if r["dl_path"] and not r["dl_path"].replace("\\", "/").startswith(f"{tid}/")]
        if elsewhere:
            return "已下载在共享URL他帖目录(未入池?)"   # v2 应已入池配对，残留即异常
        return "downloaded但本树无媒体(查)"
    if dead and len(dead) == len(rows):
        return "media全死链"
    return f"未下载{dict(Counter(r['dl_status'] for r in rows))}"


# ---------- 媒体对象（内容身份去重） ----------
def build_pool(entries: list[dict]) -> dict:
    """entries: [{rel, abs}] -> {cid: {"raw","n_*","paths","abs","size","external"}}"""
    pool: dict[str, dict] = {}
    for e in entries:
        base = os.path.basename(e["rel"])
        stem = os.path.splitext(base)[0]
        try:
            size = os.path.getsize(e["abs"])
        except OSError:
            continue
        cid = f"{os.path.normcase(base)}|{size}"
        if cid not in pool:
            stripped = strip_quality(stem)
            pool[cid] = {"raw": stem, "n_raw": norm(stem),
                         "n_stripped": norm(stripped), "n_tag": norm(strip_tag(stripped)),
                         "paths": [], "abs": e["abs"], "rel": e["rel"],
                         "size": size, "external": e.get("external", False)}
        pool[cid]["paths"].append(e["rel"])
    return pool


def tiers_of(pool: dict) -> dict:
    """同名（normcase basename 去扩展）不同体积 -> 画质档分组 {name: [cid 按体积降序]}"""
    by_name = defaultdict(list)
    for cid, c in pool.items():
        by_name[c["raw"].casefold()].append(cid)
    return {k: sorted(v, key=lambda c: -pool[c]["size"])
            for k, v in by_name.items() if len(v) > 1}


# ---------- 全树素材 ----------
topics: dict[str, dict] = {}
for dirpath, _dn, fns in os.walk(DEST):
    rel_dir = os.path.relpath(dirpath, DEST)
    if rel_dir == ".":
        continue
    tid = rel_dir.split(os.sep)[0]
    if not tid.isdigit():
        continue
    t = topics.setdefault(tid, {"vid_entries": [], "aud_entries": [], "scripts": []})
    for fn in fns:
        ext = os.path.splitext(fn)[1].lower()
        rel = os.path.join(rel_dir, fn).replace(os.sep, "/")
        abspath = os.path.join(dirpath, fn)
        if ext in VIDEO_EXTS:
            t["vid_entries"].append({"rel": rel, "abs": abspath})
        elif ext in AUDIO_EXTS:
            t["aud_entries"].append({"rel": rel, "abs": abspath})
        elif ext in SCRIPT_EXTS:
            t["scripts"].append({"rel": rel, "abs": abspath})

# 帖 EroLink dl_path 指到的媒体入池（跨帖共享 URL 的真实落点）
for tid, t in topics.items():
    for url in topic_links.get(int(tid), []):
        r = link_by_url.get(url)
        if not r or r["kind"] not in ("media", "source") or r["dl_status"] != "downloaded" or not r["dl_path"]:
            continue
        rel = r["dl_path"].replace("\\", "/")
        if os.path.normcase(rel).split("/")[0] == tid:
            continue    # 本帖树内已有（walk 覆盖）
        abspath = os.path.join(DEST, rel)
        if os.path.isdir(abspath):
            # gofile 文件夹链接：dl_path 记的是目录本身（331228 三帖共享案），
            # 目录下全部媒体入池，名字层自会精确挑出各自的那只
            for dp, _dn2, fns in os.walk(abspath):
                for fn in fns:
                    e2 = os.path.splitext(fn)[1].lower()
                    if e2 in VIDEO_EXTS or e2 in AUDIO_EXTS:
                        rel2 = os.path.relpath(os.path.join(dp, fn), DEST).replace(os.sep, "/")
                        (t["vid_entries"] if e2 in VIDEO_EXTS else t["aud_entries"]).append(
                            {"rel": rel2, "abs": os.path.join(dp, fn), "external": True})
            continue
        if not os.path.isfile(abspath):
            continue
        ext = os.path.splitext(rel)[1].lower()
        if ext in VIDEO_EXTS:
            t["vid_entries"].append({"rel": rel, "abs": abspath, "external": True})
        elif ext in AUDIO_EXTS:
            t["aud_entries"].append({"rel": rel, "abs": abspath, "external": True})

# ---------- 匹配 ----------
def name_layers(stem: str, pool: dict):
    base, axis = strip_axis(stem)
    n_raw, n_base = norm(stem), norm(base)
    n_stag = norm(strip_tag(base))
    by_layer = defaultdict(list)
    for cid, c in pool.items():
        if os.path.normcase(stem) == os.path.normcase(c["raw"]):
            by_layer["exact" if not axis else "axis+exact"].append(cid)
            continue
        if axis and os.path.normcase(base) == os.path.normcase(c["raw"]):
            by_layer["axis+exact"].append(cid)
            continue
        if n_raw in (c["n_raw"], c["n_stripped"]) or (axis and n_base in (c["n_raw"], c["n_stripped"])):
            by_layer["fuzzy" if not axis else "axis+fuzzy"].append(cid)
            continue
        if n_stag and n_stag == c["n_tag"]:
            by_layer["tagstrip" if not axis else "axis+tagstrip"].append(cid)
            continue
        a, b = n_base, c["n_stripped"]
        if len(a) >= CONTAIN_MIN and len(b) >= CONTAIN_MIN and (a in b or b in a):
            by_layer["contain"].append(cid)
    order = ["exact", "axis+exact", "fuzzy", "axis+fuzzy", "tagstrip", "axis+tagstrip", "contain"]
    return [(m, by_layer[m]) for m in order if by_layer.get(m)]


rows_out = []
method_stat = Counter()
conf_stat = Counter()
unmatched = []
review = []          # 画质档默认/低置信，人工复核清单
ambiguous = []

for tid in sorted(topics, key=int):
    t = topics[tid]
    if not t["scripts"]:
        continue
    # 逻辑脚本（同名同体积归并）
    logi: dict[tuple, dict] = {}
    for s in t["scripts"]:
        base = os.path.basename(s["rel"])
        key = (os.path.normcase(base), os.path.getsize(s["abs"]))
        if key not in logi:
            logi[key] = {"stem": os.path.splitext(base)[0], "abs": s["abs"],
                         "rel": s["rel"], "paths": []}
        logi[key]["paths"].append(s["rel"])

    vid_pool = build_pool(t["vid_entries"])
    aud_pool = build_pool(t["aud_entries"])
    vid_tiers = tiers_of(vid_pool)
    aud_tiers = tiers_of(aud_pool)

    def resolve(stem, sd, pool, tiers, prefix=""):
        """返回 (cid|None, method, extra_note)；ambiguous 另记。"""
        layers = name_layers(stem, pool)
        for m, cands in layers:
            if len(cands) == 1:
                return cands[0], prefix + m, ""
            # 同名画质档：时长分不开（内容同时长）默认大件；脚本时长已知时
            # 改挑 |Δdur| 最小那档（脚本配它写的那个剪辑）
            name = pool[cands[0]]["raw"].casefold()
            if all(pool[c]["raw"].casefold() == name for c in cands) and len(cands) > 1:
                order = tiers.get(name, cands)
                pick, note = order[0], f"档{len(cands)}选1默认大件 备选{len(cands)-1}"
                if sd is not None:
                    deltas = [((abs(d - sd) if (d := media_dur(pool[c]["rel"], pool[c]["abs"]))
                                is not None else None), c) for c in order]
                    known = [x for x in deltas if x[0] is not None]
                    if known:
                        best = min(known, key=lambda x: x[0])
                        if best[0] <= DUR_WEAK:
                            pick, note = best[1], f"档{len(cands)}选1Δ最小 备选{len(cands)-1}"
                return pick, prefix + m + "+画质档", note
            if sd is not None:
                hit = [c for c in cands
                       if (d := media_dur(pool[c]["rel"], pool[c]["abs"])) is not None
                       and abs(d - sd) <= DUR_TIGHT]
                if len(hit) == 1:
                    return hit[0], prefix + m + "+dur挑", ""
            ambiguous.append((tid, stem, prefix + m,
                              [pool[c]["rel"] for c in cands]))
            return None, "ambiguous", ""
        # 名字层全空 -> 时长全树探
        if sd is not None and pool:
            cand = [c for c in pool
                    if (d := media_dur(pool[c]["rel"], pool[c]["abs"])) is not None
                    and abs(d - sd) <= DUR_TIGHT]
            if len(cand) == 1:
                return cand[0], prefix + "dur", ""
            if len(cand) > 1:
                ambiguous.append((tid, stem, prefix + "dur探",
                                  [pool[c]["rel"] for c in cand]))
                return None, "ambiguous", ""
        return None, None, ""

    for key in sorted(logi):
        s = logi[key]
        sd = script_dur(s["abs"])
        cid, method, extra = resolve(s["stem"], sd, vid_pool, vid_tiers)
        if cid is None and method is None:
            cid, method, extra = resolve(s["stem"], sd, aud_pool, aud_tiers, prefix="audio:")
        single_note = ""
        if cid is None and method is None and len(vid_pool) == 1:
            k = next(iter(vid_pool))
            d = media_dur(vid_pool[k]["rel"], vid_pool[k]["abs"]) if sd is not None else None
            if sd is None or d is None or abs(d - sd) <= DUR_WEAK:
                cid, method = k, "single-video"
            else:
                single_note = f"唯一视频时长对不上(脚本{sd:.0f}s vs 视频{d:.0f}s,分集/剪辑?)"
        elif cid is None and method is None and len(vid_pool) == 0 and len(aud_pool) == 1:
            k = next(iter(aud_pool))
            d = media_dur(aud_pool[k]["rel"], aud_pool[k]["abs"]) if sd is not None else None
            if sd is None or d is None or abs(d - sd) <= DUR_WEAK:
                cid, method = k, "single-audio"
            else:
                single_note = f"唯一音频时长对不上(脚本{sd:.0f}s vs 音频{d:.0f}s)"

        target, dur_mark, prov_mark = "", "", ""
        conf = "-"
        if method == "ambiguous":
            conf = "?"
        elif cid is not None:
            pool = aud_pool if method.startswith("audio") or method == "single-audio" else vid_pool
            c = pool[cid]
            target = c["rel"]
            dur_mark = extra
            if sd is not None:
                d = media_dur(c["rel"], c["abs"])
                if d is not None:
                    delta = d - sd
                    dur_mark += " " if dur_mark else ""
                    dur_mark += ("dur✓" if abs(delta) <= DUR_TIGHT else
                                 (f"Δ{delta:+.1f}s" if abs(delta) <= DUR_WEAK
                                  else f"dur✗{delta:+.0f}s"))
            pv = prov.get(os.path.normcase(target))
            prov_mark = pv or ""
            if c.get("external"):
                prov_mark += " [跨帖]"
            if len(c["paths"]) > 1:
                prov_mark += f" [镜像x{len(c['paths'])}]"
            conf = {"exact": "A", "axis+exact": "A", "fuzzy": "A-", "axis+fuzzy": "A-",
                    }.get(method, "")
            if "+画质档" in method:
                conf = "B"
            elif method in ("tagstrip", "axis+tagstrip", "contain"):
                conf = "B+" if "dur✓" in dur_mark else "B"
            elif method.endswith("+dur挑"):
                conf = "A-" if ("exact" in method or "fuzzy" in method) else "B+"
            elif method == "dur" or method == "audio:dur":
                conf = "B"
            elif method.startswith("audio:"):
                conf = "A" if "exact" in method else ("A-" if "fuzzy" in method else "B+")
            elif method == "single-video" or method == "single-audio":
                conf = "C"

        mirror = f" [脚本镜像x{len(s['paths'])}]" if len(s["paths"]) > 1 else ""
        if method is None:
            reason = single_note or (media_state(int(tid))
                                     if (not vid_pool and not aud_pool) else "帖内有媒体但无命中")
            method_stat["unmatched"] += 1
            conf_stat["-"] += 1
            unmatched.append((tid, s["rel"], reason))
            rows_out.append((tid, s["rel"], "--", "", reason, "-", sd, mirror))
        else:
            method_stat[method] += 1
            conf_stat[conf] += 1
            if conf in ("B", "C"):
                review.append((tid, s["rel"], method, target, dur_mark))
            rows_out.append((tid, s["rel"], method, target, dur_mark, conf, sd,
                             mirror + ((" " + prov_mark) if prov_mark else "")))

paired_targets = {r[3] for r in rows_out if r[3]}
all_vids = [e["rel"] for t in topics.values() for e in t["vid_entries"]]
vid_no_script = sorted(set(all_vids) - paired_targets)

# ---------- 输出 ----------
n_scripts = len(rows_out)
print(f"话题目录 {len(topics)}；逻辑脚本 {n_scripts}；视频条目 {len(all_vids)}"
      f"（无任何脚本配上的 {len(vid_no_script)}）")
print("\n=== 方法分布 ===")
for k, v in method_stat.most_common():
    print(f"  {v:4}  {k}")
print("\n=== 置信分布 ===")
for k, v in sorted(conf_stat.items()):
    print(f"  {v:4}  {k}")
print("\n=== 未配归因 ===")
for k, v in Counter(r for _, _, r in unmatched).most_common():
    print(f"  {v:4}  {k}")
print(f"\n=== 人工复核清单（画质档默认/低置信 B、C）共 {len(review)} ===")
for tid, rel, m, tgt, mark in review[:30]:
    print(f"  {tid}  [{m}]  {os.path.basename(rel)[:55]}")
    if tgt:
        print(f"        -> {os.path.basename(tgt)[:65]}  {mark}")
if len(review) > 30:
    print(f"  ... 共 {len(review)}")
print(f"\n=== ambiguous（真歧义，人工）共 {len(ambiguous)} ===")
seen = set()
shown = 0
for tid, stem, m, cands in ambiguous:
    k = (tid, stem)
    if k in seen:
        continue
    seen.add(k)
    shown += 1
    if shown > 20:
        break
    print(f"  {tid}  [{m}]  {stem[:60]}")
    for c in cands[:4]:
        print(f"        候选 {os.path.basename(c)[:70]}")

try:
    json.dump(_dur_cache, open(DUR_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
except OSError:
    pass

with open(REPORT, "w", encoding="utf-8") as f:
    f.write(f"配对决策表草案（只读，v3 逻辑）  生成 {time.strftime('%Y-%m-%d %H:%M')}\n")
    f.write(f"逻辑脚本 {n_scripts}；方法 {dict(method_stat)}；置信 {dict(conf_stat)}\n")
    cur = None
    for tid, srel, m, tgt, mark, conf, sd, extra in sorted(rows_out):
        if tid != cur:
            cur = tid
            f.write(f"\n--- topic {tid} ---\n")
        line = f"  [{conf:>2}|{m:<22}] {os.path.basename(srel)[:66]}{extra}"
        if tgt:
            line += f"\n      -> {tgt[:100]}"
            if mark:
                line += f"  {mark}"
        elif m != "--":
            line += "\n      .. (见 ambiguous 明细)"
        f.write(line + "\n")
    f.write("\n=== 未配明细 ===\n")
    for tid, rel, reason in unmatched:
        f.write(f"  {tid}  {rel}  -- {reason}\n")
    f.write("\n=== 真歧义(ambiguous)明细 ===\n")
    for tid, stem, m, cands in ambiguous:
        f.write(f"  {tid}  [{m}]  {stem}\n")
        for c in cands:
            f.write(f"        候选 {c}\n")
    f.write("\n=== 人工复核（画质档 Δ最小/默认大件、B 与 C 置信）===\n")
    for tid, rel, m, tgt, mark in review:
        f.write(f"  {tid}  [{m}]  {rel}\n        -> {tgt}  {mark}\n")
    f.write(f"\n=== 无脚本配上的视频 {len(vid_no_script)} ===\n")
    for v in vid_no_script:
        f.write(f"  {v}\n")

print(f"\n全表已写 {REPORT}")
