# 流媒体 source 覆盖度 + 链接级闭环盘点（只读）。前身 _script_only_stats.py 是接入前的
# 一次性分桶（已随 playground 清理删除，报告存 archive/playground_history/_script_only_topics.md）；
# 本脚本接棒接入后的两个新问题：
#   1) source 站哪些已有 adapter（帖可收）、哪些没接（后续接入候选清单）
#   2) 已接入站的 EroLink 闭环：dl_status 分布、非终态数、落盘字节
# 输出分两层：stdout 只有聚合数 + adapter 类名（无域名，可直接跑不触名单）；
# 域名明细全写报告文件 data/eroscripts/streaming_coverage.txt。
# 用法：python playground/eroscripts/stats/_streaming_coverage.py [--since 2026-04-01] [--all]
import os
import sys
import json
import argparse
from collections import Counter
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.downloader.adapters import adapter_for, all_hosts
from scrape_all.sites.eroscripts.store import TopicStore, DL_FINAL
from scrape_all.storage.models import EroLink, EroTopicItem

DB = os.path.join(ROOT, "data", "eroscripts.db")
REPORT = os.path.join(ROOT, "data", "eroscripts", "streaming_coverage.txt")


def host_of(u):
    n = urlsplit(u).netloc.lower()
    return n[4:] if n.startswith("www.") else n


def mb(n):
    return f"{n / 1048576:.1f}MB"


ap = argparse.ArgumentParser()
ap.add_argument("--since", default="2026-04-01",
                help="created_at 下界（UTC ISO 前缀），默认 2026-04-01（consume 同款 guard）")
ap.add_argument("--all", action="store_true", help="不过滤时间，看全量")
args = ap.parse_args()
since = "" if args.all else args.since

with TopicStore(DB) as store:
    topics = [t for t in store.db.QueryRecords(EroTopicItem)
              if t.stat in (2, 3, 5)      # 只看 parse 过的（含挂起），与旧盘点同口径
              and (not since or (t.created_at or "") >= since)]
    src_rows = [r for r in store.db.QueryRecords(
        EroLink, where="kind = ?", params=("source",))]

# —— 帖级扫描：source 链接按站聚合，帖分桶（全接入 / 部分接入 / 纯未接入）——
host_topics, host_links = Counter(), Counter()   # 站 -> 帖数 / 链接数
covered_t, mixed_t, pure_t = [], [], []
n_with_src = 0
for t in topics:
    try:
        links = json.loads(t.links_json or "[]")
    except Exception:
        links = []
    srcs = [host_of((l or {}).get("url") or "") for l in links
            if (l or {}).get("kind") == "source"]
    srcs = [h for h in srcs if h]
    if not srcs:
        continue
    n_with_src += 1
    hs = set(srcs)
    for h in hs:
        host_topics[h] += 1
    host_links.update(srcs)
    covered = {h for h in hs if h in all_hosts()}
    if not covered:
        pure_t.append((t, sorted(hs)))
    elif covered == hs:
        covered_t.append(t)
    else:
        mixed_t.append((t, sorted(hs - covered)))

# —— EroLink 闭环（kind=source 全表；登记不过滤时间，这里同口径给全量）——
rows_by_host = {}
for r in src_rows:
    rows_by_host.setdefault(r.host, []).append(r)

lines = []


def rep(s=""):
    lines.append(s)


rep(f"== source 站点覆盖（已解析帖 stat=2/3/5，created_at >= {since or '不过滤'}）==")
rep(f"{'站点':<30}{'帖数':>5}{'链接数':>6}  adapter")
for h, n in host_topics.most_common():
    a = adapter_for(f"https://{h}/")
    rep(f"{h:<30}{n:>5}{host_links[h]:>6}  {a.__class__.__name__ if a else '-'}")

rep()
rep("== 纯未接入 source 帖清单（后续接入候选，按帖时间升序）==")
for t, hs in sorted(pure_t, key=lambda x: x[0].topic_id):
    rep(f"[{t.stat}] {t.topic_id}  {t.created_at[:10]}  {', '.join(hs)}")

rep()
rep("== EroLink kind=source 闭环（全表，无时间过滤）==")
for h, rows in sorted(rows_by_host.items(), key=lambda kv: -len(kv[1])):
    st = dict(Counter(r.dl_status for r in rows))
    nonfinal = sum(1 for r in rows if r.dl_status not in DL_FINAL)
    size = sum(r.dl_size or 0 for r in rows)
    rep(f"{h:<30}{len(rows):>4} 条  {st}  非终态 {nonfinal}  落盘 {mb(size)}")

os.makedirs(os.path.dirname(REPORT), exist_ok=True)
with open(REPORT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

# —— stdout：聚合数 + adapter 类名，不出现域名 ——
registered = all_hosts()
reg_hosts = sorted(h for h in host_topics if h in registered)
unreg_hosts = sorted(h for h in host_topics if h not in registered)
scope = f"created_at >= {since}" if since else "不过滤"
print(f"已解析帖(stat=2/3/5，{scope}) {len(topics)}，带 source 链接 {n_with_src} 帖；"
      f"source 站 {len(host_topics)} 家：已接入 {len(reg_hosts)}，未接入 {len(unreg_hosts)}")
for h in reg_hosts:
    a = adapter_for(f"https://{h}/")
    rows = rows_by_host.get(h, [])
    st = dict(Counter(r.dl_status for r in rows))
    print(f"  [{a.__class__.__name__}] EroLink {len(rows)} 条 {st} "
          f"非终态 {sum(1 for r in rows if r.dl_status not in DL_FINAL)} "
          f"落盘 {mb(sum(r.dl_size or 0 for r in rows))}")
unreg_rows = [r for h, rows in rows_by_host.items()
              if h not in registered for r in rows]
if unreg_rows:
    print(f"  未接入站 EroLink {len(unreg_rows)} 条 "
          f"{dict(Counter(r.dl_status for r in unreg_rows))}（登记语义：source 未跟即 skipped）")
print(f"帖分桶：全接入 {len(covered_t)} {dict(Counter(t.stat for t in covered_t))}，"
      f"部分接入 {len(mixed_t)}，纯未接入 {len(pure_t)}（候选清单见报告）")
print(f"报告已写 {REPORT}")
