# 只读实验：解压前普查——J:\es_scrape 上的档案文件清点 + zip 内容窥视。
#   - 档案按扩展名清点，join EroLink（dl_path）拿 host/kind 归属；盘上未被引用的档案单列
#   - zip 用 stdlib 开列 namelist：条目类型分布（视频/脚本/嵌套档案/杂物/其他）、
#     解压后总体积、加密标志（flag_bits & 0x1）、zip-slip 危险路径、超长路径、
#     同 archive 内重名、rar/7z 只计数列明（stdlib 读不了）
#   - J 盘剩余空间 vs 解压后增量估算
# 库只读（mode=ro），盘只 walk 只读 zip 元信息，不写任何东西。
import os
import shutil
import sqlite3
import sys
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB = os.path.join(ROOT, "data", "eroscripts.db")
DEST = r"J:\es_scrape"

VIDEO_EXT = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".m4v", ".mpg", ".mpeg", ".ts", ".flv"}
SCRIPT_EXT = {".funscript", ".lua"}
ARCHIVE_EXT = {".zip", ".rar", ".7z"}
JUNK_NAMES = {"__macosx", ".ds_store", "thumbs.db", "desktop.ini"}

db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row
rows = db.execute(
    "SELECT url, host, kind, dl_path, dl_size FROM EroLink "
    "WHERE dl_status='downloaded' AND dl_path IS NOT NULL AND dl_path != ''"
).fetchall()
by_path = {os.path.normcase(r["dl_path"].replace("/", os.sep)): r for r in rows}

# --- 盘上档案清点 ---
archives = []            # (abs, rel_norm, size, db_row|None)
for dirpath, _dirnames, filenames in os.walk(DEST):
    for fn in filenames:
        ext = os.path.splitext(fn)[1].lower()
        if ext not in ARCHIVE_EXT:
            continue
        p = os.path.join(dirpath, fn)
        rel = os.path.normcase(os.path.relpath(p, DEST))
        try:
            sz = os.path.getsize(p)
        except OSError:
            continue
        archives.append((p, rel, sz, by_path.get(rel)))

print(f"=== 档案清点：盘上 {len(archives)} 个 ===")
by_ext = Counter(os.path.splitext(rel)[1].lower() for _, rel, _, _ in archives)
print(f"扩展名分布: {dict(by_ext)}")
total_c = sum(sz for _, _, sz, _ in archives)
print(f"压缩包总体积: {total_c/1024/1024/1024:.2f}GB")
orphan = [a for a in archives if a[3] is None]
print(f"未被 EroLink 引用（orphan）: {len(orphan)}")
for p, rel, sz, _ in orphan[:10]:
    print(f"  {sz/1024/1024:9.1f}MB  {rel}")
by_host = Counter(r["host"] for *_, r in archives if r)
print(f"引用行的 host 分布: {dict(by_host)}")
by_kind = Counter(r["kind"] for *_, r in archives if r)
print(f"引用行的 kind 分布: {dict(by_kind)}")

# --- zip 内容窥视 ---
zip_stats = []           # 每包一条 dict
unextracted_total = 0    # 解压后增量估算（去重后总体积）
print(f"\n=== zip 内容窥视（{by_ext.get('.zip', 0)} 个）===")
for p, rel, sz, r in archives:
    if not p.lower().endswith(".zip"):
        continue
    st = {"rel": rel, "size": sz, "entries": 0, "video": 0, "script": 0,
          "nested": 0, "junk": 0, "other": 0, "dirs": 0, "uncompressed": 0,
          "encrypted": 0, "slip": 0, "toolong": 0, "dupname": 0,
          "err": None}
    names_seen = set()
    try:
        with zipfile.ZipFile(p) as z:
            for info in z.infolist():
                if info.is_dir():
                    st["dirs"] += 1
                    continue
                st["entries"] += 1
                st["uncompressed"] += info.file_size
                name = info.filename.replace("\\", "/")
                base = name.rsplit("/", 1)[-1]
                ext = os.path.splitext(base)[1].lower()
                top_seg = name.split("/", 1)[0].lower()
                if base.lower() in JUNK_NAMES or top_seg == "__macosx":
                    st["junk"] += 1
                elif ext in VIDEO_EXT:
                    st["video"] += 1
                elif ext in SCRIPT_EXT:
                    st["script"] += 1
                elif ext in ARCHIVE_EXT:
                    st["nested"] += 1
                else:
                    st["other"] += 1
                if info.flag_bits & 0x1:
                    st["encrypted"] += 1
                norm = name.lower()
                if norm.startswith("/") or ".." in norm.split("/"):
                    st["slip"] += 1
                dest_len = len(os.path.join(os.path.dirname(p), *name.split("/")))
                if dest_len > 250:
                    st["toolong"] += 1
                key = norm.rsplit("/", 1)[-1] if "/" not in norm else norm
                if key in names_seen:
                    st["dupname"] += 1
                names_seen.add(key)
    except Exception as e:
        st["err"] = f"{type(e).__name__}: {e}"
    zip_stats.append(st)

err_n = sum(1 for s in zip_stats if s["err"])
print(f"可开列目录: {len(zip_stats) - err_n} / 打不开: {err_n}")
for s in zip_stats:
    if s["err"]:
        print(f"  [ERR] {s['rel']}  {s['err']}")
agg = Counter()
for s in zip_stats:
    for k in ("entries", "video", "script", "nested", "junk", "other",
              "encrypted", "slip", "toolong", "dupname"):
        agg[k] += s[k]
unc_total = sum(s["uncompressed"] for s in zip_stats)
print(f"条目合计: {dict(agg)}")
print(f"解压后总体积（未去重）: {unc_total/1024/1024/1024:.2f}GB vs 压缩 {total_c/1024/1024/1024:.2f}GB")
for k in ("encrypted", "slip", "toolong", "dupname"):
    if agg[k]:
        print(f"  !! {k} 非零，涉及包：")
        for s in zip_stats:
            if s[k]:
                print(f"     {s[k]:3d}  {s['rel']}")

# 内容形态分布：纯视频包 / 纯脚本包 / 混合包 / 空包
shape = Counter()
mix_examples = []
for s in zip_stats:
    if s["err"]:
        shape["打不开"] += 1
    elif s["entries"] == 0:
        shape["空包"] += 1
    elif s["video"] and s["script"]:
        shape["混合(视频+脚本)"] += 1
        mix_examples.append(s["rel"])
    elif s["video"]:
        shape["纯视频"] += 1
    elif s["script"]:
        shape["纯脚本"] += 1
    else:
        shape["其他内容"] += 1
print(f"包形态分布: {dict(shape)}")
if mix_examples:
    print(f"混合包示例（前 8）:")
    for rel in mix_examples[:8]:
        print(f"  {rel}")

# 大包 top10（解压耗时/空间主要来源）
print("\n压缩体积 top10:")
for p, rel, sz, r in sorted(archives, key=lambda a: -a[2])[:10]:
    host = r["host"] if r else "?"
    print(f"  {sz/1024/1024:9.1f}MB  {host:12}  {rel}")

# --- 磁盘空间 ---
try:
    usage = shutil.disk_usage(DEST)
    print(f"\nJ 盘: 总 {usage.total/1024**3:.1f}GB / 已用 {usage.used/1024**3:.1f}GB / 剩余 {usage.free/1024**3:.1f}GB")
except OSError as e:
    print(f"J 盘空间读取失败: {e}")

# --- rar/7z 明细 ---
others = [(p, rel, sz, r) for p, rel, sz, r in archives if not p.lower().endswith(".zip")]
if others:
    print(f"\n非 zip 档案 {len(others)} 个明细：")
    for p, rel, sz, r in others:
        host = r["host"] if r else "?"
        print(f"  {os.path.splitext(rel)[1]}  {sz/1024/1024:9.1f}MB  {host:12}  {rel}")

# --- 已解压痕迹：同名目录存在？（zip 旁有同名夹视为可能已手动解过）---
hint = 0
for p, rel, sz, r in archives:
    stem = os.path.splitext(p)[0]
    if os.path.isdir(stem):
        hint += 1
print(f"\nzip 旁存在同名目录（可能已手动解压）: {hint}")
