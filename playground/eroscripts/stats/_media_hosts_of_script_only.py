# 只读：category=14 且 since 内「只下载了脚本、没下载媒体」的帖——它们带的媒体链接
# （media 网盘 / source 流媒体）落在哪些站、什么状态。stdout 不打印流媒体域名
# （网盘域名不敏感可直出），含域名的完整明细写报告文件。
import os
import sys
import json
import argparse
from collections import Counter
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import EROS_CATEGORY_ID
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink, EroTopicItem

REPORT = os.path.join(ROOT, "data", "eroscripts", "script_only_media_hosts.txt")

ap = argparse.ArgumentParser()
ap.add_argument("--since", default="2026-04-01", help="created_at 下界，默认 2026-04-01")
args = ap.parse_args()

with TopicStore(os.path.join(ROOT, "data", "eroscripts.db")) as store:
    rows = {r.url: r for r in store.db.QueryRecords(EroLink)}
    topics = [t for t in store.db.QueryRecords(EroTopicItem)
              if t.category_id == EROS_CATEGORY_ID
              and (t.created_at or "") >= args.since]

script_only = []          # (topic, media_rows) media_rows=该帖未下载的媒体链接行
for t in sorted(topics, key=lambda x: x.created_at):
    try:
        links = json.loads(t.links_json or "[]")
    except Exception:
        links = []
    dl_kinds, media_rows = Counter(), []
    for l in links:
        r = rows.get((l or {}).get("url") or "")
        if r is None:
            continue
        if r.dl_status == "downloaded":
            dl_kinds[r.kind] += 1
        elif r.kind in ("media", "source"):
            media_rows.append(r)
    if dl_kinds.get("script", 0) > 0 and dl_kinds.get("media", 0) == 0 \
            and dl_kinds.get("source", 0) == 0:
        script_only.append((t, media_rows))

no_media = [t for t, m in script_only if not m]
with_media = [(t, m) for t, m in script_only if m]

# 站聚合：host -> (帖数, 链接数, kind 集合, dl_status 分布)
host_stat = {}
for t, m in with_media:
    for r in m:
        e = host_stat.setdefault(r.host, [0, 0, set(), Counter()])
        e[1] += 1
        e[2].add(r.kind)
        e[3][r.dl_status] += 1
for t, m in with_media:
    for h in {r.host for r in m}:
        host_stat[h][0] += 1

lines = []


def rep(s=""):
    lines.append(s)


rep(f"== 只下载了脚本、没下载媒体的帖（category={EROS_CATEGORY_ID}，"
    f"created_at >= {args.since}）带媒体链接的 {len(with_media)} 帖 ==")
rep(f"{'站点':<30}{'帖数':>5}{'链接数':>6}  kind       dl_status")
for h, (tn, ln, kinds, st) in sorted(host_stat.items(), key=lambda kv: -kv[1][1]):
    rep(f"{h:<30}{tn:>5}{ln:>6}  {'/'.join(sorted(kinds)):<10} {dict(st)}")
rep()
rep("== 逐帖明细（仅带媒体链接的）==")
for t, m in with_media:
    rep(f"[{t.stat}] {t.topic_id}  {t.created_at[:10]}  {t.title}")
    for r in m:
        rep(f"    {r.kind:<7} {r.dl_status:<10} {r.url}")

os.makedirs(os.path.dirname(REPORT), exist_ok=True)
with open(REPORT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

# —— stdout：聚合 + 网盘域名直出，流媒体域名不出现 ——
print(f"只下载了脚本、没下载媒体：{len(script_only)} 帖；"
      f"其中完全没有媒体链接 {len(no_media)} 帖，带媒体链接但未下载 {len(with_media)} 帖"
      f"（合计 {sum(len(m) for _, m in with_media)} 条）")
kinds_st = Counter((r.kind, r.dl_status) for _, m in with_media for r in m)
print(f"未下载媒体链接 (kind, dl_status) 分布：{dict(kinds_st)}")
pan = [(h, v) for h, v in host_stat.items() if "media" in v[2]]
src = [(h, v) for h, v in host_stat.items() if "source" in v[2]]
print(f"媒体站 {len(host_stat)} 家：网盘类 {len(pan)}，流媒体类 {len(src)}（域名见报告）")
for h, (tn, ln, kinds, st) in sorted(pan, key=lambda kv: -kv[1][1]):
    print(f"  {h:<30} 帖{tn:>3} 链接{ln:>3} {dict(st)}")
print(f"报告已写 {REPORT}")
