
"""冒烟 5 帖产物核验：es_norm 全树清单 + 媒体产物 ffprobe + EroNorm 落库状态。"""
import json
import os
import sqlite3
import subprocess

FFPROBE = r"E:\Program Files\ffmpeg\bin\ffprobe.exe"
DST = r"J:\es_norm"
REPO = r"F:\Python\ScrapeAll"
IDS = ["307720", "323371", "324307", "328160", "329619"]
MEDIA_EXTS = (".mp4", ".webm", ".wav")

print("== es_norm 树")
files = []
for tid in IDS:
    d = os.path.join(DST, tid)
    for dirpath, _dirs, fns in os.walk(d):
        for fn in sorted(fns):
            p = os.path.join(dirpath, fn)
            files.append(p)
            rel = os.path.relpath(p, DST).replace(os.sep, "/")
            print(f"  {os.path.getsize(p)/1024/1024:9.2f}MB  {rel}")
print(f"共 {len(files)} 文件")

print("\n== 媒体产物 ffprobe（转码该 960x540 / webm wav 原样）")
for p in files:
    if os.path.splitext(p)[1].lower() not in MEDIA_EXTS:
        continue
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", p],
        capture_output=True, text=True)
    try:
        info = json.loads(out.stdout)
    except ValueError:
        print(f"  [probe 失败] {p}")
        continue
    vs = next((s for s in info.get("streams", [])
               if s.get("codec_type") == "video"), None)
    aud = next((s for s in info.get("streams", [])
                if s.get("codec_type") == "audio"), None)
    dur = float(info.get("format", {}).get("duration") or 0)
    name = os.path.basename(p)
    if vs:
        print(f"  {name[:60]:60s} {vs['width']}x{vs['height']} "
              f"{vs.get('codec_name')} {dur:8.1f}s "
              f"音轨 {'有(' + aud.get('codec_name', '?') + ')' if aud else '无'}")
    else:
        print(f"  {name[:60]:60s} 音频 {aud.get('codec_name')} {dur:8.1f}s")

print("\n== EroNorm 落库")
con = sqlite3.connect(os.path.join(REPO, "data", "eroscripts.db"))
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT status, action, kind, COUNT(*) n FROM EroNorm "
    "GROUP BY status, action, kind ORDER BY status, kind").fetchall()
for r in rows:
    print(f"  {r['status']:6s} {r['action']:10s} {r['kind']:15s} {r['n']}")
bad = con.execute(
    "SELECT target_path, status FROM EroNorm WHERE status != 'done'").fetchall()
for r in bad:
    print(f"  [非 done] {r['target_path']} {r['status']}")
con.close()
