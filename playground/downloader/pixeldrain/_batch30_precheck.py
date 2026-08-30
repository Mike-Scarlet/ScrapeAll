
"""放量前快查：/d 形态链接的 dl_status 分布与待捞存量。只读。"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

with TopicStore(os.path.join(_ROOT, "data", "eroscripts.db")) as store:
  rows = store.db.QueryRecords(EroLink)
  pd = [r for r in rows if r.host == "pixeldrain.com"]
  d_form = [r for r in pd if "/d/" in r.url]
  print("pixeldrain 全部:", len(pd), " dl_status:", dict(Counter(r.dl_status for r in pd)))
  print("/d 形态:", len(d_form), " dl_status:", dict(Counter(r.dl_status for r in d_form)))
  pend = [r for r in d_form if r.dl_status == "pending"]
  print("/d 待捞(alive+pending):", len(pend))
  done = [r for r in d_form if r.dl_status == "downloaded"]
  tot = sum((r.dl_size or 0) for r in done)
  print(f"/d 已捞 downloaded: {len(done)} 合计 {tot / 1024 / 1024 / 1024:.2f}GB")
