
"""只读查库：还没做 adapter 的 MEDIA_HOSTS 各家，2026-04 至今链接量 + 全量对比。"""
import json
import os
import sqlite3
from collections import Counter
from urllib.parse import urlparse

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB = os.path.join(_ROOT, "data", "eroscripts.db")

# 已接 adapter 的 host（不算 catbox 子域、eros uploads 站内附件）
DONE = {
    "catbox.moe", "litter.catbox.moe", "litterbox.catbox.moe",
    "pixeldrain.com",
    "gofile.io",
    "mega.nz", "mega.link", "mega.is", "app.mega.nz", "mega.co.nz",
}

# topic_parse.MEDIA_HOSTS 全表减去已接入的，就是"还没做基建"的
PENDING = {
    "drive.google.com", "docs.google.com",
    "disk.yandex.com", "yadi.sk",
    "pan.baidu.com",
    "mediafire.com", "app.mediafire.com", "www.mediafire.com",
    "dropbox.com", "www.dropbox.com", "dl.dropboxusercontent.com",
    "1fichier.com", "ww1.1fichier.com",
    "workupload.com",
    "send.cm",
    "anonfiles.com",
    "terabox.com",
}

con = sqlite3.connect(DB)
rows = con.execute(
    "select topic_id, created_at, links_json from EroTopicItem "
    "where links_json is not null").fetchall()
con.close()
print(f"扫描 {len(rows)} 个有 links 的 topic")

CUT = "2026-04-01"
since_links = Counter()      # host -> 2026-04 后链接数
all_links = Counter()        # host -> 全量链接数
since_topics = Counter()     # host -> 2026-04 后出现的 topic 数
since_month = {}             # host -> Counter(月份)
samples = {}                 # host -> 最多 3 条样本

for t_id, dt, blob in rows:
    d = (dt or "")[:10]
    try:
        arr = json.loads(blob)
    except (ValueError, TypeError):
        continue
    hit_hosts = set()
    for item in arr:
        u = (item or {}).get("url") or ""
        host = urlparse(u).netloc.lower().removeprefix("www.")
        if host in PENDING or host in DONE:
            key = host
        else:
            # 捕捉 MEDIA_HOSTS 之外的遗漏形态（如 m.githubusercontent 之类不在此例，
            # 这里只关心 PENDING 家族的变体子域）
            base = ".".join(host.split(".")[-2:]) if host.count(".") >= 1 else host
            if base in ("mediafire.com", "dropbox.com", "1fichier.com", "workupload.com",
                        "yandex.com", "yadi.sk", "terabox.com", "anonfiles.com", "send.cm"):
                key = base
            else:
                continue
        all_links[key] += 1
        if d >= CUT:
            since_links[key] += 1
            hit_hosts.add(key)
            since_month.setdefault(key, Counter())[d[:7]] += 1
            if len(samples.setdefault(key, [])) < 3:
                samples[key].append(u)
    for h in hit_hosts:
        since_topics[h] += 1

print(f"\n=== 2026-04-01 至今（PENDING 家族，按 host）===")
tot = 0
for h, n in since_links.most_common():
    tot += n
    months = dict(sorted(since_month.get(h, {}).items()))
    print(f"  {h:28s} {n:4d} 条 / {since_topics[h]:3d} topic  按月 {months}")
print(f"  合计 {tot} 条")

print(f"\n=== 全量（同族，含 2026-04 前）===")
for h, n in all_links.most_common():
    if h in DONE:
        continue
    print(f"  {h:28s} {n:4d} 条")

print("\n=== 2026-04 后 PENDING 各家样本（每家至多 3 条）===")
for h, _ in since_links.most_common():
    for u in samples[h]:
        print(f"  {h}\t{u[:110]}")
