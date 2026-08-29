# 一次性（只读）：核验选中的 10 帖——除该站外还有没有别的非终态链接
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.sites.eroscripts.store import TopicStore, DL_FINAL
from scrape_all.storage.models import EroLink, EroTopicItem

IDS = [301123, 307119, 307472, 307473, 307864, 307865, 307868,
       307870, 308104, 308133]

with TopicStore(os.path.join(ROOT, "data", "eroscripts.db")) as store:
  for tid in IDS:
    t = store.db.QueryOne(EroTopicItem, where="topic_id = ?", params=(tid,))
    urls = [(l or {}).get("url") or "" for l in json.loads(t.links_json or "[]")]
    urls = [u for u in urls if u]
    marks = ",".join("?" for _ in urls)
    rows = {r.url: r for r in store.db.QueryRecords(
        EroLink, where=f"url in ({marks})", params=tuple(urls))}
    nonfinal = [(rows[u].host, rows[u].dl_status) for u in urls
                if u in rows and rows[u].dl_status not in DL_FINAL]
    missing = [u for u in urls if u not in rows]
    print(f"topic={tid} stat={t.stat} links={len(urls)} "
          f"非终态={nonfinal or '无'} 未登记={len(missing)}")
