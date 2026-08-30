
"""6 组挂起（normalize pending）决策取证：每组列出候选脚本的
大小/mtime/动作数/末动作时间（时长），以及帖内链接发现顺序（first_seen
≈ 帖面顺序）。只读本地。"""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

ROOT = r"J:\es_scrape"
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data", "eroscripts.db")

TOPICS = [307720, 307726, 312236, 324307, 328160, 329619]
EXTRA_DIRS = {329619: [322746]}   # 跨帖媒体池


def fs_info(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception as e:
        return f"    [json 读不了: {e}]"
    acts = data.get("actions") or []
    if not acts:
        return "    [无动作]"
    dur = acts[-1]["at"] / 1000
    return f"    动作 {len(acts):5d}  时长 {dur:7.1f}s"


con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
for tid in TOPICS:
    title = con.execute("SELECT title FROM EroTopicItem WHERE topic_id=?",
                        (tid,)).fetchone()
    print(f"\n== topic {tid}  {title['title'] if title else '?'}")
    for d in [os.path.join(ROOT, str(tid))] + \
             [os.path.join(ROOT, str(x)) for x in EXTRA_DIRS.get(tid, [])]:
        for dirpath, _dirs, files in os.walk(d):
            for fn in sorted(files):
                if not fn.lower().endswith(".funscript"):
                    continue
                p = os.path.join(dirpath, fn)
                st = os.stat(p)
                rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
                print(f"  {rel}")
                print(f"    {st.st_size/1024:8.1f}KB  "
                      f"mtime {time.strftime('%m-%d %H:%M', time.localtime(st.st_mtime))}")
                print(fs_info(p))
    rows = con.execute(
        "SELECT url, kind, dl_path FROM EroLink "
        "WHERE first_topic_id=? ORDER BY rowid", (tid,)).fetchall()
    print(f"  -- 帖内链接（发现序）{len(rows)} 条")
    for r in rows:
        print(f"    [{r['kind']}] {r['url'][:100]}"
              + (f"  -> {r['dl_path'][:60]}" if r["dl_path"] else ""))
con.close()
