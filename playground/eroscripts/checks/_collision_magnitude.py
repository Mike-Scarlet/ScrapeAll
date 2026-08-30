# 只读：同名覆盖量级测算。
#   A. 已发生：EroLink 按非空 dl_path 分组，>1 行的组里：
#      - 组内 dl_size 全等且等于盘上文件 -> 同内容镜像（已存在 skip，无损失）
#      - 有行 size != 盘上文件 -> 被覆盖，丢的就是这些行的字节
#   B. 未来暴露面：stat=2 队列将真下载的链接量（script+media）× 历史内容互撞率外推；
#      另按"帖内 ≥2 条同 host 同 kind"数互撞前置条件浓度的帖子。
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB = os.path.join(ROOT, "data", "eroscripts.db")
DEST = r"J:\es_scrape"

db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

# ---------- A. 已发生 ----------
groups = defaultdict(list)
for r in db.execute(
    "SELECT url, host, kind, dl_path, dl_size, dl_status, dl_note FROM EroLink "
    "WHERE dl_path IS NOT NULL AND dl_path != ''"
):
    groups[os.path.normcase(r["dl_path"].replace("/", os.sep))].append(dict(r))

benign = loss_groups = 0
lost_bytes = 0
loss_detail = []
for rel, rows in groups.items():
    if len(rows) < 2:
        continue
    disk = os.path.getsize(os.path.join(DEST, rel)) if os.path.exists(os.path.join(DEST, rel)) else None
    # 丢内容 = 真下载过（dl_size>0）且体积与盘上 survivor 不符的行；
    # dl_size=0 的 skipped 行是幂等"已存在"跳过（镜像链接），非损失
    lost_rows = [r for r in rows
                 if r["dl_size"] and disk is not None and r["dl_size"] != disk]
    if lost_rows:
        loss_groups += 1
        lost_bytes += sum(r["dl_size"] or 0 for r in lost_rows)
        loss_detail.append((rel, len(rows), disk, [(r["url"], r["dl_size"], r["dl_status"], r["dl_note"]) for r in rows]))
    else:
        benign += 1

total_dl = db.execute("SELECT COUNT(*) FROM EroLink WHERE dl_status='downloaded'").fetchone()[0]
print("=== A. 已发生（downloaded 全历史） ===")
print(f"已下载行: {total_dl}")
print(f"同路径多行组: 良性镜像 {benign} 组 / 内容互撞丢内容 {loss_groups} 组")
print(f"被覆盖丢失合计: {lost_bytes}B ({lost_bytes/1024/1024:.1f}MB)")
for rel, n, disk, rows in loss_detail:
    print(f"\n  {rel}  组内{n}行 盘上{disk}B")
    for url, size, st, note in rows:
        mark = "  <-- 被覆盖" if size != disk else ""
        print(f"    {size:>12}B {st:10} {url[:80]} {note or ''}{mark}")

# ---------- B. 未来暴露面 ----------
kind_count = Counter()
topic_multi = Counter()   # tid -> 同host同kind计数超1的组合数
for r in db.execute("SELECT topic_id, links_json FROM EroTopicItem WHERE stat=2"):
    try:
        links = json.loads(r["links_json"] or "[]")
    except ValueError:
        continue
    per_hk = Counter()
    for l in links:
        if not (l or {}).get("url"):
            continue
        kind = l.get("kind")
        if kind not in ("script", "media"):
            continue
        kind_count[kind] += 1
        per_hk[(urlparse(l["url"]).netloc, kind)] += 1
    for hk, c in per_hk.items():
        if c >= 2:
            topic_multi[hk] += 1

future = sum(kind_count.values())
past_rate = loss_groups / total_dl if total_dl else 0
print(f"\n=== B. 未来暴露面（stat=2 存量 868 帖） ===")
print(f"将真下载链接: script {kind_count['script']} + media {kind_count['media']} = {future}")
print(f"历史内容互撞率: {loss_groups}/{total_dl} = {past_rate:.3%}")
print(f"外推期望互撞: {future * past_rate:.1f} 例")
print(f"(单例损失参考: 已发生 3 例中位约 {sorted([82316, 136766, 299620706])[1]/1024/1024:.0f}MB，最坏 {299620706/1024/1024:.0f}MB)")
print("\n帖内 ≥2 条同 host 同 kind（互撞前置条件浓度）Top:")
for (host, kind), c in topic_multi.most_common(10):
    print(f"  {host:35} {kind:7} {c} 帖")
print(f"合计命中帖次: {sum(topic_multi.values())}")
