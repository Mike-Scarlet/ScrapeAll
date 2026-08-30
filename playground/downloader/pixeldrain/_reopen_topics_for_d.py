
"""把仍有非终态链接的 CONSUMED 帖复位回 PARSED，让正式编排器能选中它们。

只动 stat 一个字段；跑完编排器扫尾会自动推回 3（全终态）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.sites.eroscripts.store import Stat, TopicStore
from scrape_all.storage.models import EroLink, EroTopicItem

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DL_FINAL = frozenset(("downloaded", "skipped", "dead", "manual", "exhausted"))

with TopicStore(os.path.join(_ROOT, "data", "eroscripts.db")) as store:
  links = store.db.QueryRecords(EroLink)
  open_tids = sorted({r.first_topic_id for r in links if r.dl_status not in DL_FINAL})
  print(f"非终态链接挂在 {len(open_tids)} 个帖上，逐个复位 stat -> PARSED：")
  flipped = 0
  for tid in open_tids:
    t = store.db.QueryOne(EroTopicItem, where="topic_id = ?", params=(tid,))
    if t is None:
        print(f"  [{tid}] 无帖子记录，跳过")
        continue
    if t.stat != int(Stat.CONSUMED):
        print(f"  [{tid}] stat={t.stat} 非 CONSUMED，跳过")
        continue
    item = EroTopicItem(topic_id=tid, stat=int(Stat.PARSED))
    store.db.RecordFieldChanged(item, ["stat"])
    store.db.Commit()
    flipped += 1
  print(f"复位 {flipped} 个帖子")
