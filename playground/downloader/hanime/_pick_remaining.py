# 一次性（只读）：清点该站全部剩余 pending——两个视角核对挂靠帖（链接行自带
# first_topic_id vs 全库 links_json 扫命中），审计每帖其他非终态/未登记链接
# （防连带消费），最后给出可整批收口的 stat=3 帖 ids csv 与 --since 下限
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.sites.eroscripts.store import TopicStore, DL_FINAL
from scrape_all.storage.models import EroLink, EroTopicItem

DB = os.path.join(ROOT, "data", "eroscripts.db")

with TopicStore(DB) as store:
  pend_rows = store.db.QueryRecords(
      EroLink, where="host='hanime1.me' AND dl_status='pending'")
  pend = {r.url for r in pend_rows}
  print(f"该站 pending 总数: {len(pend)}")

  # 视角一：pending 行自带的 first_topic_id
  by_first = {}
  for r in pend_rows:
    by_first.setdefault(r.first_topic_id, []).append(r.url)
  print(f"\n[first_topic_id 视角] {len(by_first)} 帖")
  for tid, urls in sorted(by_first.items()):
    t = store.db.QueryOne(EroTopicItem, where="topic_id = ?", params=(tid,))
    print(f"  topic={tid} stat={t.stat if t else '帖无'} "
          f"created={t.created_at if t else '?'} hits={len(urls)}")

  # 视角二：全部帖 links_json 扫 pending 命中（覆盖跨帖共享 URL）
  rows = store.db.QueryRecords(EroTopicItem, where="links_json IS NOT NULL")
  holders = []
  for t in rows:
    try:
      urls = [(l or {}).get("url") or "" for l in json.loads(t.links_json or "[]")]
    except ValueError:
      continue
    urls = [u for u in urls if u]
    if not any(u in pend for u in urls):
      continue
    marks = ",".join("?" for _ in urls)
    reg = {r.url: r for r in store.db.QueryRecords(
        EroLink, where=f"url in ({marks})", params=tuple(urls))}
    nonfinal = [(reg[u].host, reg[u].dl_status) for u in urls
                if u in reg and reg[u].dl_status not in DL_FINAL]
    missing = [u for u in urls if u not in reg]
    holders.append((t, nonfinal, len(missing), urls))

  print(f"\n[links_json 视角] 命中帖 {len(holders)} 个")
  covered = set()
  for t, nonfinal, nmiss, urls in sorted(holders, key=lambda x: x[0].created_at or ""):
    others = [nf for nf in nonfinal if nf[0] != "hanime1.me"]
    print(f"  topic={t.topic_id} stat={t.stat} created={t.created_at or '(空)'} "
          f"hits={sum(1 for u in urls if u in pend)} "
          f"其他非终态={others or '无'} 未登记={nmiss}")
    covered.update(u for u in urls if u in pend)

  uncovered = pend - covered
  if uncovered:
    print(f"\n!! {len(uncovered)} 条 pending 不在任何 links_json 命中帖里:")
    for u in sorted(uncovered):
      print(f"  {u}")
  else:
    print("\n覆盖核对: 全部 pending 都有命中帖")

  clean = [(t, nonfinal, nmiss) for t, nonfinal, nmiss, _ in holders
           if t.stat == 3
           and all(h == "hanime1.me" for h, _ in nonfinal) and nmiss == 0]
  ids = [t.topic_id for t, _, _ in sorted(clean, key=lambda x: x[0].created_at or "")]
  print(f"\n可整批收口的帖（stat=3、非终态全是本站、0 未登记）: {len(ids)}")
  print(f"ids={','.join(str(i) for i in ids)}")
  if ids:
    first = min((t.created_at for t, _, _ in clean if t.created_at), default="?")
    print(f"--since 下限: {first}")
