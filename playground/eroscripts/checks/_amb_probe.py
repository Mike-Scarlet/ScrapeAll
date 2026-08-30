# 只读：ambiguous 典型案的候选体积/路径对照 + 2 个"downloaded但本树无视频"排查
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEST = r"J:\es_scrape"
DB = r"F:\Python\ScrapeAll\data\eroscripts.db"

CASES = {
    "309327": ["3919140 騎乗位で搾り取ってくれるraちゃん_音声あり_.mp4"],
    "310118": ["9p4z2f.mp4", "cgqe0d.mp4"],
    "311626": ["[Kamuo] Norma Vid + Gifs.mp4"],
    "307860": ["[Harechippai (はれ)] ケイ.mp4", "[Harechippai (はれ)] ケイ.404683.mp4"],
    "314488": ["ammy - (sex dance) catch.mp4"],
}
print("=== 同名/同长候选体积对照 ===")
for tid, names in CASES.items():
    print(f"--- {tid} ---")
    tdir = os.path.join(DEST, tid)
    for dirpath, _dn, fns in os.walk(tdir):
        for fn in fns:
            if any(fn == n or fn.startswith(os.path.splitext(n)[0]) for n in names):
                rel = os.path.relpath(os.path.join(dirpath, fn), tdir)
                print(f"  {os.path.getsize(os.path.join(dirpath, fn)):>12}B  {rel}")

db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row
print("\n=== 'downloaded但本树无视频(查)' 案源 ===")
# 重跑归因：找有脚本、无视频、但 media downloaded 的帖
import json
link_by_url = {r["url"]: r for r in db.execute(
    "SELECT url, kind, dl_status, dl_path FROM EroLink")}
for r in db.execute("SELECT topic_id, links_json FROM EroTopicItem"):
    urls = [l.get("url") for l in json.loads(r["links_json"] or "[]") if l.get("url")]
    rows = [link_by_url[u] for u in urls if u in link_by_url
            and link_by_url[u]["kind"] in ("media", "source")]
    dl = [x for x in rows if x["dl_status"] == "downloaded"]
    if not dl:
        continue
    tid = str(r["topic_id"])
    tdir = os.path.join(DEST, tid)
    has_video = False
    if os.path.isdir(tdir):
        for _dp, _dn, fns in os.walk(tdir):
            if any(os.path.splitext(f)[1].lower() in
                   {".mp4", ".mkv", ".webm", ".wmv", ".avi", ".mov", ".ts"} for f in fns):
                has_video = True
                break
    elsewhere = [x["dl_path"] for x in dl
                 if x["dl_path"] and not x["dl_path"].replace("\\", "/").startswith(tid + "/")]
    if not has_video and not elsewhere:
        print(f"  topic {tid}: media downloaded 但树内无视频")
        for x in dl:
            print(f"    {x['dl_path']}  {x['dl_size']}B")
