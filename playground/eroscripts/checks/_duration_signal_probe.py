# 只读：③续——funscript metadata/range 内容样本 + 本机能否读视频时长（ffprobe/pymediainfo）
import json
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEST = r"J:\es_scrape"

print("=== funscript metadata / range 样本（3 个） ===")
shown = 0
for dirpath, _d, files in os.walk(DEST):
    for fn in sorted(files):
        if not fn.endswith(".funscript") or shown >= 3:
            continue
        p = os.path.join(dirpath, fn)
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        acts = data.get("actions") or []
        print(f"  {os.path.relpath(p, DEST)}")
        print(f"    range={data.get('range')}  last_at={acts[-1]['at'] if acts else '-'}")
        md = data.get("metadata")
        print(f"    metadata={json.dumps(md, ensure_ascii=False)[:200]}")
        shown += 1
    if shown >= 3:
        break

print("\n=== 视频时长读取手段 ===")
ffprobe = shutil.which("ffprobe")
ffmpeg = shutil.which("ffmpeg")
print(f"  ffprobe: {ffprobe}  ffmpeg: {ffmpeg}")
try:
    import pymediainfo  # noqa
    print("  pymediainfo: 已装")
except ImportError:
    print("  pymediainfo: 未装")

if ffprobe:
    # 拿 307119 那对 fuzzy 对子实测：视频时长 vs 脚本 99669ms
    v = os.path.join(DEST, "307119", "[パントン] 大神環 _ Ogami Tamaki.mp4")
    r = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", v],
        capture_output=True, text=True,
    )
    print(f"  307119 视频 ffprobe duration: {r.stdout.strip()}s  (脚本 last_at=99.669s)")

# 没有 ffprobe 就用 python 读 mp4 的 mvhd 时长（纯只读，手撸 box 解析）
if not ffprobe:
    import struct

    def mp4_duration(path):
        with open(path, "rb") as f:
            data = f.read(4 * 1024 * 1024)  # moov 通常在前几 MB（或尾部，尾部则放弃）
        i = data.find(b"mvhd")
        if i < 0:
            return None
        ver = data[i + 4]
        if ver == 1:
            timescale, dur = struct.unpack(">IQ", data[i + 20:i + 32])
        else:
            timescale, dur = struct.unpack(">II", data[i + 16:i + 24])
        return dur / timescale if timescale else None

    v = os.path.join(DEST, "307119", "[パントン] 大神環 _ Ogami Tamaki.mp4")
    d = mp4_duration(v)
    print(f"  307119 视频 mvhd 时长(手撸解析): {d}s  (脚本 last_at=99.669s)")
