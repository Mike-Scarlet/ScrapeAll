
"""剩余 /d 待捞的 37 条挂的帖子：stat 与 created_at，核对是否在正式 guard 视野内。只读。"""
import os
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink, EroTopicItem

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

with TopicStore(os.path.join(_ROOT, "data", "eroscripts.db")) as store:
  rows = store.db.QueryRecords(EroLink, where="host = ?", params=["pixeldrain.com"])
  tids = sorted({r.first_topic_id for r in rows
                 if urlsplit(r.url).path.startswith("/d/") and r.dl_status == "pending"})
  print(f"/d 待捞 37 条挂在 {len(tids)} 个帖上；帖子 stat/created_at 对照（guard 默认 2026-04-01）：")
  stat_names = {2: "PARSED(2)", 3: "CONSUMED(3)"}
  out_of_guard = 0
  for tid in tids:
    t = store.db.QueryOne(EroTopicItem, where="topic_id = ?", params=(tid,))
    if t is None:
        print(f"  [{tid}] 无帖子记录!")
        continue
    in_guard = (t.created_at or "") >= "2026-04-01"
    if not in_guard:
        out_of_guard += 1
    print(f"  [{tid}] stat={stat_names.get(t.stat, t.stat)}  {t.created_at}  "
          f"{'guard内' if in_guard else '** guard 外 **'}")
  print(f"\nguard 外帖子数: {out_of_guard}")
