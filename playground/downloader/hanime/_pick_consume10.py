# 一次性（只读）：为放量挑帖子——扫描 stat=3 帖的 links_json，数每帖挂的
# 该站 pending 链接数，给出恰好凑 TARGET 条的帖子组合（created_at 升序、
# 优先 1 命中帖；stat=2 未消费过的旧帖有未登记链接会连带消费，不选）。
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink, EroTopicItem

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 10
DB = os.path.join(ROOT, "data", "eroscripts.db")

with TopicStore(DB) as store:
  pend = {r.url for r in store.db.QueryRecords(
      EroLink, where="host='hanime1.me' AND dl_status='pending'")}
  print(f"该站 pending 总数: {len(pend)}")

  rows = store.db.QueryRecords(EroTopicItem,
                               where="stat=3 AND links_json IS NOT NULL")
  per_topic = []   # (topic_id, stat, created_at, 命中数)
  for t in rows:
    try:
      urls = [(l or {}).get("url") or "" for l in json.loads(t.links_json or "[]")]
    except ValueError:
      continue
    hits = sum(1 for u in urls if u in pend)
    if hits:
      per_topic.append((t.topic_id, t.stat, t.created_at, hits))

  per_topic.sort(key=lambda x: (x[3] != 1, x[2] or "", x[0]))
  picked, total = [], 0
  for r in per_topic:
    if total + r[3] <= TARGET:
      picked.append(r)
      total += r[3]
    if total == TARGET:
      break
  print(f"\n建议组合（恰好 {total} 条，{len(picked)} 帖）：")
  for r in picked:
    print(f"  topic={r[0]} created={r[2] or '(空)'} 命中={r[3]}")
  print(f"\nids={','.join(str(r[0]) for r in picked)}")
  print(f"--since 下限: {picked[0][2] if picked else '?'}")
