# 一次性：topic 314864 的 mega 链接已人工捞回 pending（ero_links.py set），
# 但帖子在链接转 exhausted 时被推到 stat=3，consume 队列只见 stat=2——
# 把帖子打回 2，让下一批 pass 带新 40s 渲染超时重探该链接。
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink, EroTopicItem

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "data", "eroscripts.db")

with TopicStore(DB) as store:
  t = store.db.QueryOne(EroTopicItem, where="topic_id = ?", params=(314864,))
  print(f"before: stat={t.stat}")
  t.stat = 2
  store.db.RecordFieldChanged(t, ["stat"])
  store.db.Commit()
  t2 = store.db.QueryOne(EroTopicItem, where="topic_id = ?", params=(314864,))
  link = store.db.QueryOne(EroLink, where="url = ?",
      params=("https://mega.nz/folder/NwcnGTbT#S1SNTBE9Xs8BJ36UM8KfAA",))
  print(f"after: stat={t2.stat}; mega link dl_status={link.dl_status} "
        f"dl_retries={link.dl_retries} probe_status={link.probe_status}")
