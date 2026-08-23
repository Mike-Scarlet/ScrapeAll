
"""本地 sqlite 链接形态普查 v2（只读库，不开浏览器、不发网络请求）。
逐条解析 links_json，按 host 聚合后续要接的各家。"""
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from urllib.parse import urlparse

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(_ROOT, "data", "eroscripts.db")

TARGETS = ("gofile.io", "mega.nz", "mega.link", "drive.google.com",
           "docs.google.com", "workupload.com")

con = sqlite3.connect(DB)
links = []
for (t_id, blob) in con.execute(
        "select topic_id, links_json from EroTopicItem where links_json is not null"):
    try:
        arr = json.loads(blob)
    except (ValueError, TypeError):
        continue
    for item in arr:
        u = (item or {}).get("url") or ""
        if any(h in u for h in TARGETS):
            links.append((t_id, item.get("kind"), u, item.get("name")))

print(f"共 {len(links)} 条目标链接\n")
by_host = defaultdict(list)
for t_id, kind, u, name in links:
    by_host[urlparse(u).netloc].append((t_id, kind, u, name))

for host, items in sorted(by_host.items(), key=lambda kv: -len(kv[1])):
    print(f"== {host}: {len(items)} 条")
    shapes = Counter()
    sample = {}
    kinds = Counter()
    for t_id, kind, u, name in items:
        p = urlparse(u)
        shape = f"{p.scheme}://{p.netloc}{re.sub(r'[A-Za-z0-9_\-]{5,}', '{id}', p.path)}"
        shapes[shape] += 1
        kinds[kind] += 1
        sample.setdefault(shape, (t_id, u, name))
    print(f"   kind 分布: {dict(kinds)}")
    for shape, n in shapes.most_common(10):
        t_id, u, name = sample[shape]
        print(f"   {n:4d}  {shape}")
        print(f"        e.g. topic={t_id} {u!r} name={name!r}")
    print()
