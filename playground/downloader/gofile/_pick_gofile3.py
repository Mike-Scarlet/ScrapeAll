
"""取库里第 13-20 条 gofile 链接（本地只读）"""
import json
import os
import sqlite3

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
con = sqlite3.connect(os.path.join(_ROOT, "data", "eroscripts.db"))
out = []
for (lj,) in con.execute(
        "SELECT links_json FROM EroTopicItem WHERE stat=2 AND links_json IS NOT NULL"):
    try:
        arr = json.loads(lj)
    except (ValueError, TypeError):
        continue
    for l in arr:
        u = l.get("url") or ""
        if "gofile.io/d/" in u and u not in out:
            out.append(u)
for u in out[12:20]:
    print(f'--url "{u}"')
