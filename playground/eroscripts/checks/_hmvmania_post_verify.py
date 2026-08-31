"""放量终验：8 帖落盘件 vs EroLink 落库 vs probe 体积三对账 + ffprobe 抽查"""
import json
import os
import sqlite3
import subprocess

con = sqlite3.connect("data/eroscripts.db")
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT url, dl_status, dl_path, dl_size, dl_note, first_topic_id FROM EroLink "
    "WHERE url LIKE '%hmvmania.com/video/%' ORDER BY first_topic_id").fetchall()

total = 0
files = []
for r in rows:
    p = os.path.join(r"J:\es_scrape", r["dl_path"])
    on_disk = os.path.getsize(p) if os.path.exists(p) else -1
    ok = on_disk == r["dl_size"]
    total += max(on_disk, 0)
    files.append(p)
    print(f"topic={r['first_topic_id']} {r['dl_status']:10} disk={on_disk:>12,} "
          f"db={r['dl_size']:>12,} {'OK' if ok else '!!不一致'} {os.path.basename(p)}")
print(f"合计 {total:,} B = {total / 1024 / 1024:.1f}MB")
print("topics stat:", con.execute(
    "SELECT stat, COUNT(*) FROM EroTopicItem WHERE topic_id IN (319931,321390,322171,"
    "323524,325066,325182,329255,329989) GROUP BY stat").fetchall())

# 抽查 ffprobe（319931 本尊 + 最大件 322171）
for p in (files[0], files[1]):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", p], capture_output=True, text=True)
    info = json.loads(r.stdout)
    v = next(s for s in info["streams"] if s.get("codec_type") == "video")
    a = next((s for s in info["streams"] if s.get("codec_type") == "audio"), None)
    print(f"ffprobe {os.path.basename(p)[:60]}: dur={info['format']['duration']}s "
          f"{v.get('codec_name')} {v.get('width')}x{v.get('height')} "
          f"audio={a.get('codec_name') if a else None}")
