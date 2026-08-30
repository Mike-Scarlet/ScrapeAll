# 只读：3 个待解 zip 的 EroLink 引用 + 中央目录窥探 + 新批次视频命名形态
import os
import sqlite3
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DB = r"F:\Python\ScrapeAll\data\eroscripts.db"
DEST = r"J:\es_scrape"

db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

rels = ["326896/JeanOffice.zip",
        "329078/R_Senya Luluka 1.zip",
        "331305/[Anniversary Special] The Triple Threat - A MokuStory - AV1.zip"]
print("=== 3 个待解 zip：库行 + 包内 ===")
for rel in rels:
    rows = db.execute("SELECT url, host, kind, dl_status, dl_size FROM EroLink "
                      "WHERE dl_path = ?", (rel,)).fetchall()
    print(rel)
    for r in rows:
        print(f"    {r['host']} {r['kind']} {r['dl_status']} {r['dl_size']}B")
    try:
        with zipfile.ZipFile(os.path.join(DEST, rel)) as z:
            for info in z.infolist()[:10]:
                print(f"    zip内: {info.filename}  {info.file_size}")
            print(f"    ... 共 {len(z.infolist())} 条")
    except Exception as e:
        print("    zip 窥探失败:", e)

# 新批次视频命名形态：rule34 落的帖 + hanime 落的帖各看几眼
print("\n=== 流媒体帖命名形态（视频 vs 脚本） ===")
for tid in ["309906", "326671", "311902", "331228", "324307", "323524", "325182"]:
    tdir = os.path.join(DEST, tid)
    print(f"--- {tid} ---")
    for dirpath, _dn, fns in os.walk(tdir):
        rel_dir = os.path.relpath(dirpath, tdir)
        vids = [f for f in fns if os.path.splitext(f)[1].lower() in
                {".mp4", ".mkv", ".webm", ".wmv", ".avi", ".mov", ".ts"}]
        scrs = [f for f in fns if f.lower().endswith(".funscript")]
        if vids or scrs:
            where = "根" if rel_dir == "." else rel_dir
            for v in vids[:6]:
                print(f"  [V|{where}] {v[:90]}")
            for s in scrs[:6]:
                print(f"  [S|{where}] {s[:90]}")
            if len(scrs) > 6:
                print(f"  [S|{where}] ...共 {len(scrs)} 个脚本")

# 流媒体视频与 funscript 的 host 来源对照：近48h source 链接的 dl_path 样本
print("\n=== 近 48h source 下载行样本（命名来源） ===")
for r in db.execute(
        "SELECT host, dl_path FROM EroLink WHERE dl_status='downloaded' "
        "AND kind='source' AND dl_at >= '2026-08-28' ORDER BY dl_at DESC LIMIT 20"):
    print(f"  {r['host']:20} {r['dl_path']}")
