
"""全局在途快查：EroLink 全表 dl_status 分布 + stat=2 未消费帖子数。只读。"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink, EroTopicItem

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

with TopicStore(os.path.join(_ROOT, "data", "eroscripts.db")) as store:
  links = store.db.QueryRecords(EroLink)
  print("EroLink 全表:", len(links), "行")
  print("  dl_status:", dict(Counter(r.dl_status for r in links)))
  nonfinal = [r for r in links if r.dl_status not in ("downloaded", "skipped", "dead", "manual", "exhausted")]
  print("  非终态行:", len(nonfinal), " 分布(按host):", dict(Counter(r.host for r in nonfinal)))
  topics = store.db.QueryRecords(EroTopicItem)
  print("EroTopicItem:", len(topics), "行  stat:", dict(Counter(t.stat for t in topics)))
  stat2 = [t for t in topics if t.stat == 2]
  if stat2:
    stat2.sort(key=lambda t: t.created_at or "")
    print(f"  stat=2 未消费帖子 {len(stat2)} 个（guard 2026-04-01 内 "
          f"{sum(1 for t in stat2 if (t.created_at or '') >= '2026-04-01')} 个）：")
    for t in stat2[:10]:
        print(f"    [{t.topic_id}] {t.created_at}")
