# 盘点：「有 script 无 media」帖子的分桶 + 流媒体 source 站点分布（只读查询）
# 用法：python playground/_script_only_stats.py [--since 2026-04-01] [--all]
#   --since  created_at 下界（UTC ISO 前缀，字符串比较），默认 2026-04-01（consume 同款 guard）
#   --all    不过滤时间，看全量
import os
import sys
import json
import argparse
from urllib.parse import urlsplit
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroTopicItem

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "data", "eroscripts.db")

# 疑似域名表漏认的真·文件托管（ MEDIA_HOSTS 之外的下载直链 ）
MISSED_HOSTS = {"pixeldrain.net", "mantisx.catbox.cloud", "litter.catbox.moe"}
SPLIT_EXTS = (".001", ".002", ".003", ".004", ".005", ".zip", ".7z", ".rar")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def host_of(u):
    n = urlsplit(u).netloc.lower()
    return n[4:] if n.startswith("www.") else n


def load_parsed(store, since):
    for t in store.db.QueryRecords(EroTopicItem):
        if t.stat not in (2, 3, 5):    # 只看 parse 过的（含挂起）
            continue
        if since and (t.created_at or "") < since:
            continue
        try:
            links = json.loads(t.links_json or "[]")
        except Exception:
            links = []
        yield t, links


def source_stats(rows):
    """rows: [(topic, links)] -> (站点->帖数, 站点->链接数, 单帖站点数分布)"""
    ht, hl, multi = Counter(), Counter(), Counter()
    for _, links in rows:
        hs = set()
        for l in links:
            if (l or {}).get("kind") == "source":
                h = host_of(l.get("url") or "")
                hl[h] += 1
                hs.add(h)
        for h in hs:
            ht[h] += 1
        multi[len(hs)] += 1
    return ht, hl, multi


def dump_sources(title, rows):
    ht, hl, multi = source_stats(rows)
    print(f"\n== {title} ==")
    print(f"帖子数 {len(rows)}，source 链接 {sum(hl.values())} 条，"
          f"单帖站点数分布 {dict(sorted(multi.items()))}（1=单源，2+=多源）")
    print(f"{'站点':<28}{'帖数':>5}{'链接数':>6}")
    for h, n in ht.most_common():
        print(f"{h:<28}{n:>5}{hl[h]:>6}")


ap = argparse.ArgumentParser()
ap.add_argument("--since", default="2026-04-01",
                help="created_at 下界（UTC ISO 前缀），默认 2026-04-01")
ap.add_argument("--all", action="store_true", help="不过滤时间，看全量")
args = ap.parse_args()
since = "" if args.all else args.since

with TopicStore(DB) as store:
    parsed = list(load_parsed(store, since))

bucket_missed, bucket_src, bucket_pay = [], [], []
all_with_media_or_no_script = []
for t, links in parsed:
    kinds = Counter((l or {}).get("kind") or "?" for l in links)
    if kinds.get("script", 0) == 0 or kinds.get("media", 0) > 0:
        all_with_media_or_no_script.append((t, links))
        continue
    missed = [l.get("url") for l in links
              if (l or {}).get("kind") == "other"
              and (host_of(l.get("url") or "") in MISSED_HOSTS
                   or (host_of(l.get("url") or "") == "files.catbox.moe"
                       and (l.get("url") or "").lower().endswith(SPLIT_EXTS)))]
    if missed:
        bucket_missed.append((t, missed))
    elif kinds.get("source", 0) > 0:
        bucket_src.append((t, links))
    else:
        bucket_pay.append((t, links))

total = len(parsed)
scope = f"created_at >= {since}" if since else "不过滤"
print(f"已解析帖(stat=2/3/5，{scope}) {total}，"
      f"其中有 script 无 media {len(bucket_missed) + len(bucket_src) + len(bucket_pay)}：")
print(f"  漏提取修复候选: {len(bucket_missed)} (stat {dict(Counter(t.stat for t, _ in bucket_missed))})")
for t, urls in sorted(bucket_missed, key=lambda x: x[0].topic_id):
    print(f"    [{t.stat}] {t.topic_id}  {t.created_at[:10]}")
    for u in urls:
        print(f"        {u}")
print(f"  只有流媒体 source: {len(bucket_src)} (stat {dict(Counter(t.stat for t, _ in bucket_src))})")
print(f"  只有 paywall/画廊/社交: {len(bucket_pay)} (stat {dict(Counter(t.stat for t, _ in bucket_pay))})")

dump_sources("桶二（script 无 media）流媒体分布", bucket_src)
dump_sources("对照：全部已解析帖中带 source 的", [(t, l) for t, l in parsed
      if any((x or {}).get("kind") == "source" for x in l)])
