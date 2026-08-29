
"""取库里第 7-12 条 gofile 链接（本地只读；探活另行报批）"""
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
batch2 = out[6:12]
print(f"库内去重共 {len(out)} 条；第 7-12 条：")
for u in batch2:
    print(f"   {u}")
print("\nprobe_downloader 命令参数：")
print("  " + " ".join(f'--url "{u}"' for u in batch2))
