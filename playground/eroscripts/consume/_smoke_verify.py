
"""冒烟验收：J:\es_scrape 全部 funscript JSON 合法性 + 库内状态复核。"""
import glob
import json
import os
import sqlite3

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

print("== 落盘文件 ==")
total = 0
for p in sorted(glob.glob(r"J:\es_scrape\*\\*.funscript".replace("\\\\", "\\"))):
    d = json.load(open(p, encoding="utf-8"))
    print(f"  OK {len(d.get('actions', [])):5} actions | "
          f"{os.path.getsize(p):>7}B | {p.split(os.sep)[-1]}")
    total += os.path.getsize(p)
print(f"  共 {total} 字节")

print("\n== 库内：3 帖 stat 与链接状态 ==")
con = sqlite3.connect(os.path.join(_ROOT, "data", "eroscripts.db"))
for tid, stat in con.execute(
        "select topic_id, stat from EroTopicItem where topic_id in (307119,307299,307301)"):
    print(f"  topic {tid} stat={stat}")
for st, n in con.execute(
        "select dl_status, count(*) from EroLink where first_topic_id in "
        "(307119,307299,307301) group by 1"):
    print(f"  dl_status={st}: {n}")
print("\n== 全库 stat 分布 ==")
print(" ", dict(con.execute("select stat, count(*) from EroTopicItem group by 1")))
con.close()
