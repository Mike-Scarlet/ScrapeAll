
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import sqlite3
from scrape_all.sites.eroscripts.topic_parse import parse_topic_links
from scrape_all.sites.eroscripts.topic_files import load_topic_json

# 列出全部挂起帖（stat=5）及其链接，人工判断怎么处理
db = sqlite3.connect("data/eroscripts.db")
rows = db.execute(
    "select topic_id, title from EroTopicItem where stat=5 order by topic_id").fetchall()
print(f"挂起 topic 共 {len(rows)} 个")
for tid, title in rows:
  j = load_topic_json(tid)
  print(f"\n=== {tid} 「{title}」")
  for l in parse_topic_links(j):
    print(f"  {l.kind:7} p{l.post_number} {l.name[:36]!r:40} {l.url[:90]}")
