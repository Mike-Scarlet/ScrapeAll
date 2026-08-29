
"""只读：stat 分布 + stat=2 待消费链接池按 host/kind 分桶（去重）。"""
import json
import sqlite3
from collections import Counter
from urllib.parse import urlparse

con = sqlite3.connect("data/eroscripts.db")
print("stat 分布:", dict(con.execute(
    "select stat, count(*) from EroTopicItem group by stat").fetchall()))
rows = con.execute(
    "select links_json from EroTopicItem where stat=2 and links_json is not null"
).fetchall()
con.close()

hosts, kinds = Counter(), Counter()
seen = set()
for (lj,) in rows:
    for l in json.loads(lj):
        u = l.get("url") or ""
        if u in seen:
            continue
        seen.add(u)
        h = urlparse(u).netloc.lower().removeprefix("www.")
        hosts[h] += 1
        kinds[l.get("kind")] += 1

print(f"stat=2 去重后总链接 {len(seen)} 条")
print("link_kind:", dict(kinds))
print("Top host:")
for h, n in hosts.most_common(15):
    print(f"  {h:32s} {n}")
