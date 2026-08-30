
"""剩余 /d 待捞清单，按体积降序。只读。"""
import json
import os
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def fmt(n):
    if not n:
        return "   ?  "
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:5.2f}GB"
    return f"{n / 1024 ** 2:5.0f}MB"


with TopicStore(os.path.join(_ROOT, "data", "eroscripts.db")) as store:
  rows = store.db.QueryRecords(EroLink, where="host = ?", params=["pixeldrain.com"])
  pend = []
  for r in rows:
    path = urlsplit(r.url).path
    if not path.startswith("/d/"):
        continue
    if r.dl_status != "pending":
        continue
    try:
        meta = json.loads(r.meta_json or "{}")
    except ValueError:
        meta = {}
    pend.append((meta.get("size") or 0, meta.get("filename") or "", r))

  pend.sort(key=lambda t: -t[0])
  total = sum(s for s, _, _ in pend)
  print(f"/d 待捞 {len(pend)} 条，页标合计约 {fmt(total)}（页标是近似，集合页可能偏低）\n")
  for s, name, r in pend:
    print(f"{fmt(s)}  [{r.first_topic_id}] {r.url}" + (f"  {name}" if name else ""))
