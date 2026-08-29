# 只读审计：guard 之前创建、stat=2、且 source 链接落在已接入站的帖子——
# 它们为什么没到 3？两种可能：其余链接有非终态（真有待办），或全部链接已终态
# （只是从没被 consume 选中、没跑过 finalize 翻态）。stdout 不打印域名。
import os
import sys
import json
from collections import Counter
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.downloader.adapters import all_hosts
from scrape_all.sites.eroscripts.store import TopicStore, DL_FINAL
from scrape_all.storage.models import EroLink, EroTopicItem

GUARD = "2026-04-01"   # 与 _streaming_coverage.py 默认口径一致


def host_of(u):
    n = urlsplit(u).netloc.lower()
    return n[4:] if n.startswith("www.") else n


with TopicStore(os.path.join(ROOT, "data", "eroscripts.db")) as store:
    rows = {r.url: r for r in store.db.QueryRecords(EroLink)}
    topics = [t for t in store.db.QueryRecords(EroTopicItem)
              if t.stat == 2 and (t.created_at or "") < GUARD]

reg = all_hosts()
ready, todo = [], []          # 全链接终态 / 有非终态
nonfinal_states = Counter()   # (kind, dl_status) -> 链接数
unregistered = 0
for t in topics:
    try:
        links = json.loads(t.links_json or "[]")
    except Exception:
        links = []
    if not any((l or {}).get("kind") == "source"
               and host_of((l or {}).get("url") or "") in reg for l in links):
        continue
    urls = [(l or {}).get("url") or "" for l in links]
    urls = [u for u in urls if u]
    missing = [u for u in urls if u not in rows]
    unregistered += len(missing)
    bad = [rows[u] for u in urls if u in rows and rows[u].dl_status not in DL_FINAL]
    for r in bad:
        nonfinal_states[(r.kind, r.dl_status)] += 1
    (todo if (bad or missing) else ready).append((t, len(bad) + len(missing)))

print(f"stat=2 且 created_at < {GUARD} 且 source 含已接入站：{len(ready) + len(todo)} 帖")
print(f"  全部链接已终态（只差一次 finalize 翻 3）：{len(ready)} 帖")
print(f"  还有非终态/未登记链接（consume 真有待办）：{len(todo)} 帖，"
      f"合计 {sum(n for _, n in todo)} 条")
print(f"  非终态链接 (kind, dl_status) 分布：{dict(nonfinal_states)}；未登记 {unregistered} 条")
print(f"  待办帖非终态链接数分布：{dict(Counter(n for _, n in todo))}")
