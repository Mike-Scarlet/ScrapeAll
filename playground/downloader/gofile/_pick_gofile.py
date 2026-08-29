
"""挑 3 条固定的 gofile 观察链接（本地只读，开页面另行报批）"""
import json
import os
import sqlite3

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
con = sqlite3.connect(os.path.join(_ROOT, "data", "eroscripts.db"))
out = []
for (t_id, blob) in con.execute(
        "select topic_id, links_json from EroTopicItem where links_json like '%gofile.io/%'"):
    try:
        arr = json.loads(blob)
    except (ValueError, TypeError):
        continue
    for item in arr:
        u = (item or {}).get("url") or ""
        if "gofile.io/d/" in u:
            out.append((t_id, u, item.get("name")))
# 固定取样：最早 2 条 + 最晚 1 条（确定性，无遍历）
picked = out[:2] + out[-1:]
for t_id, u, name in picked:
    print(f"topic={t_id} {u}  name={name!r}")
