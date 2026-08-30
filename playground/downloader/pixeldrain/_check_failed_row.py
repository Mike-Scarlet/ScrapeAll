
"""看当前唯一 failed 行是不是 8K 那条。只读。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

with TopicStore(os.path.join(_ROOT, "data", "eroscripts.db")) as store:
  rows = store.db.QueryRecords(EroLink, where="dl_status = ?", params=["failed"])
  for r in rows:
    print(f"{r.url}\n  topic={r.first_topic_id} retries={r.dl_retries} size={r.dl_size}\n  note: {r.dl_note}")
