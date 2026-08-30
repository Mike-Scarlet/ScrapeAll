"""只读：stat=2 未消费帖的 links_json host 构成 + source dl_status=skipped 的 host 分布。"""
import json
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

DB = Path(__file__).resolve().parents[3] / "data" / "eroscripts.db"
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

rows = db.execute("SELECT topic_id, links_json FROM EroTopicItem WHERE stat=2").fetchall()
host_kind = Counter()
kind_only = Counter()
topics_with_links = 0
for r in rows:
    links = json.loads(r["links_json"] or "[]")
    if links:
        topics_with_links += 1
    for ln in links:
        kind = ln.get("kind") or ln.get("link_kind")
        u = ln.get("url", "")
        host = urlparse(u).netloc if "://" in u else "(相对)"
        host_kind[(host, kind)] += 1
        kind_only[kind] += 1

print(f"stat=2 帖数: {len(rows)}，其中有链接的: {topics_with_links}")
print("\n=== kind 汇总 ===")
for k, c in kind_only.most_common():
    print(f"{k}: {c}")
print("\n=== host x kind Top 30 ===")
for (host, kind), c in host_kind.most_common(30):
    print(f"{host:40} {kind:8} {c}")

print("\n=== source skipped 140 的 host 分布（EroLink） ===")
for r in db.execute("SELECT host, COUNT(*) c FROM EroLink WHERE kind='source' AND dl_status='skipped' GROUP BY host ORDER BY c DESC"):
    print(dict(r))

print("\n=== source skipped 的 dl_note 采样 ===")
for r in db.execute("SELECT host, url, dl_note FROM EroLink WHERE kind='source' AND dl_status='skipped' LIMIT 10"):
    print(dict(r))
