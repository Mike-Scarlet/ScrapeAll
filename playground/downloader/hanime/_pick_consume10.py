# 一次性（只读）：为「consume 10 条」挑帖子——扫描 stat=2/3 帖的 links_json，
# 数每帖挂的该站 pending 链接数，给出恰好凑 10 条的帖子组合（优先 stat=2
# 可直接选的、created_at 最旧的；stat=3 的需先翻回 2）。
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink, EroTopicItem

DB = os.path.join(ROOT, "data", "eroscripts.db")

with TopicStore(DB) as store:
  pend = {r.url for r in store.db.QueryRecords(
      EroLink, where="host='hanime1.me' AND dl_status='pending'")}
  print(f"该站 pending 总数: {len(pend)}")

  rows = store.db.QueryRecords(EroTopicItem,
                               where="stat in (2,3) AND links_json IS NOT NULL")
  per_topic = []   # (topic_id, stat, created_at, 命中数)
  for t in rows:
    try:
      urls = [(l or {}).get("url") or "" for l in json.loads(t.links_json or "[]")]
    except ValueError:
      continue
    hits = sum(1 for u in urls if u in pend)
    if hits:
      per_topic.append((t.topic_id, t.stat, t.created_at, hits))

  per_topic.sort(key=lambda x: (x[1] != 2, x[2] or "", x[0]))
  print("\n每帖命中（stat=2 在前，created_at 升序）：")
  for r in per_topic:
    print(f"  topic={r[0]} stat={r[1]} created={r[2] or '(空)'} 命中={r[3]}")

  picked, total = [], 0
  for r in per_topic:
    if total + r[3] <= 10:
      picked.append(r)
      total += r[3]
    if total == 10:
      break
  print(f"\n建议组合（恰好 {total} 条）：")
  for r in picked:
    print(f"  topic={r[0]} stat={r[1]} 命中={r[3]}")
  need_flip = [r[0] for r in picked if r[1] != 2]
  if need_flip:
    print(f"需翻回 stat=2 的帖子: {need_flip}")
