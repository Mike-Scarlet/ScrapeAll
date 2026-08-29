
"""挑 3 条固定的 mega 观察链接：1 条 /file/ + 2 条 /folder/（本地只读）"""
import json
import os
import sqlite3

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
con = sqlite3.connect(os.path.join(_ROOT, "data", "eroscripts.db"))
files, folders = [], []
for (lj,) in con.execute(
        "SELECT links_json FROM EroTopicItem WHERE stat=2 AND links_json IS NOT NULL"):
    try:
        arr = json.loads(lj)
    except (ValueError, TypeError):
        continue
    for l in arr:
        u = l.get("url") or ""
        if "mega.nz/file/" in u and u not in files:
            files.append(u)
        elif "mega.nz/folder/" in u and u not in folders:
            folders.append(u)
print(f"/file/ 形态 {len(files)} 条，/folder/ 形态 {len(folders)} 条")
print("观察样本（各自取最早 1-2 条，固定）：")
for u in files[:1] + folders[:2]:
    print(f"   {u}")
