# 只读：created_at >= since 的已解析帖里，哪些帖的脚本已下载、哪些帖的媒体已下载
# （媒体 = media 网盘 + source 流媒体，任意一条 downloaded 即算）。stdout 不打印域名。
import os
import sys
import json
import argparse
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import EROS_CATEGORY_ID
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink, EroTopicItem

ap = argparse.ArgumentParser()
ap.add_argument("--since", default="2026-04-01", help="created_at 下界，默认 2026-04-01")
args = ap.parse_args()

with TopicStore(os.path.join(ROOT, "data", "eroscripts.db")) as store:
    rows = {r.url: r for r in store.db.QueryRecords(EroLink)}
    topics = [t for t in store.db.QueryRecords(EroTopicItem)
              if t.category_id == EROS_CATEGORY_ID
              and (t.created_at or "") >= args.since]

scripts_t, media_t = [], []   # (topic, n) 两栏可重叠
for t in sorted(topics, key=lambda x: x.created_at):
    try:
        links = json.loads(t.links_json or "[]")
    except Exception:
        links = []
    kinds_dl = Counter()
    for l in links:
        r = rows.get((l or {}).get("url") or "")
        if r is not None and r.dl_status == "downloaded":
            kinds_dl[r.kind] += 1
    n_script = kinds_dl.get("script", 0)
    n_media = kinds_dl.get("media", 0)
    n_stream = kinds_dl.get("source", 0)
    if n_script:
        scripts_t.append((t, n_script, n_media, n_stream))
    if n_media or n_stream:
        media_t.append((t, n_script, n_media, n_stream))

print(f"created_at >= {args.since} 且 category_id={EROS_CATEGORY_ID} 的帖 共 {len(topics)} "
      f"(stat 分布 {dict(Counter(t.stat for t in topics))})")
print(f"\n== 下载了脚本的帖：{len(scripts_t)} ==")
for t, ns, nm, nv in scripts_t:
    print(f"[{t.stat}] {t.topic_id}  {t.created_at[:10]}  脚本{ns}条"
          + (f"（另有媒体{nm + nv}条）" if nm + nv else "") + f"  {t.title}")
print(f"\n== 下载了媒体的帖：{len(media_t)} ==")
for t, ns, nm, nv in media_t:
    detail = " + ".join(x for x in (f"网盘{nm}条" if nm else "", f"流媒体{nv}条" if nv else "") if x)
    print(f"[{t.stat}] {t.topic_id}  {t.created_at[:10]}  {detail}"
          + (f"（另有脚本{ns}条）" if ns else "") + f"  {t.title}")

s_ids = {t.topic_id for t, *_ in scripts_t}
m_ids = {t.topic_id for t, *_ in media_t}
both = len(s_ids & m_ids)
print(f"\n== 例外：只下载了媒体（无脚本下载）：{len(m_ids - s_ids)} ==")
for t, ns, nm, nv in media_t:
    if t.topic_id not in s_ids:
        print(f"[{t.stat}] {t.topic_id}  {t.created_at[:10]}  {t.title}")
print(f"\n== 例外：脚本媒体都没下载：{len(set(t.topic_id for t in topics) - s_ids - m_ids)} ==")
for t in topics:
    if t.topic_id in s_ids or t.topic_id in m_ids:
        continue
    try:
        links = json.loads(t.links_json or "[]")
    except Exception:
        links = []
    states = Counter()
    for l in links:
        r = rows.get((l or {}).get("url") or "")
        states[(r.kind if r else "?", r.dl_status if r else "未登记")] += 1
    print(f"[{t.stat}] {t.topic_id}  {t.created_at[:10]}  "
          f"{dict(states)}  {t.title}")
print(f"\n汇总：脚本栏 {len(scripts_t)} 帖、媒体栏 {len(media_t)} 帖；"
      f"两栏都占 {both}，只脚本 {len(s_ids) - both}，只媒体 {len(m_ids) - both}，"
      f"两者皆无 {len(topics) - len(s_ids | m_ids)}")
