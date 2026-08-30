# 只读：2 个"已下载在共享URL他帖目录(未入池?)"悬案定位
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEST = r"J:\es_scrape"
DB = r"F:\Python\ScrapeAll\data\eroscripts.db"
VID = {".mp4", ".mkv", ".webm", ".wmv", ".avi", ".mov", ".flv", ".ts", ".m4v", ".mpg", ".mpeg"}
AUD = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus"}

db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row
link_by_url = {r["url"]: r for r in db.execute(
    "SELECT url, kind, dl_status, dl_path FROM EroLink")}

for r in db.execute("SELECT topic_id, links_json FROM EroTopicItem"):
    tid = str(r["topic_id"])
    urls = [l.get("url") for l in json.loads(r["links_json"] or "[]") if l.get("url")]
    dl = [link_by_url[u] for u in urls if u in link_by_url
          and link_by_url[u]["kind"] in ("media", "source")
          and link_by_url[u]["dl_status"] == "downloaded"]
    if not dl:
        continue
    elsewhere = [x["dl_path"].replace("\\", "/") for x in dl
                 if x["dl_path"] and not x["dl_path"].replace("\\", "/").startswith(tid + "/")]
    if not elsewhere:
        continue
    tdir = os.path.join(DEST, tid)
    has_media = False
    if os.path.isdir(tdir):
        for _dp, _dn, fns in os.walk(tdir):
            if any(os.path.splitext(f)[1].lower() in VID | AUD for f in fns):
                has_media = True
                break
    if has_media:
        continue    # 树内有媒体的帖不管（那 2 案是树内无媒体的）
    print(f"=== topic {tid} 树内无媒体，media 落他帖 ===")
    for rel in elsewhere:
        p = os.path.join(DEST, rel)
        ext = os.path.splitext(rel)[1].lower()
        ok = os.path.isfile(p)
        pooled = ext in VID or ext in AUD
        print(f"    dl_path={rel}")
        print(f"      盘上存在={ok}  扩展={ext}  可入池={pooled}", end="")
        if ok:
            print(f"  {os.path.getsize(p)}B", end="")
        print()
