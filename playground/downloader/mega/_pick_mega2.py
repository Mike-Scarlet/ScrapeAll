
"""列出 2026-04 后的 25 条 mega 链接（本地只读查库，为第二批观察挑样本）。"""
import json
import os
import sqlite3
from urllib.parse import urlparse

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
con = sqlite3.connect(os.path.join(_ROOT, "data", "eroscripts.db"))

rows = con.execute(
    "select topic_id, created_at, title, links_json from EroTopicItem "
    "where links_json is not null and created_at >= '2026-04-01' "
    "order by created_at").fetchall()
seen = set()
for t_id, dt, title, blob in rows:
    for item in json.loads(blob or "[]"):
        u = (item or {}).get("url") or ""
        host = urlparse(u).netloc.lower().removeprefix("www.")
        if host not in ("mega.nz", "mega.link"):
            continue
        if u in seen:
            continue
        seen.add(u)
        kind = "file" if "/file/" in urlparse(u).path else \
               ("folder" if "/folder/" in urlparse(u).path else "other")
        print(f"{dt[:10]} {kind:6s} topic={t_id} {u}")
        print(f"          {title[:60]!r}")
print(f"\n共 {len(seen)} 条（去重后）")
