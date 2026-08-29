
import json
import sqlite3
from collections import Counter
from urllib.parse import urlsplit

db = sqlite3.connect("data/eroscripts.db")
rows = db.execute(
    "select topic_id, title, links_json, stat from EroTopicItem where stat=2").fetchall()
print(f"parsed topics: {len(rows)}")

topic_kinds = Counter()
link_kinds = Counter()
media_hosts = Counter()
no_media = 0
for tid, title, links_json, _ in rows:
  links = json.loads(links_json) if links_json else []
  kinds = {l["kind"] for l in links}
  for k in kinds:
    topic_kinds[k] += 1
  for l in links:
    link_kinds[l["kind"]] += 1
    if l["kind"] == "media":
      media_hosts[urlsplit(l["url"]).netloc] += 1
  if "script" in kinds and "media" not in kinds:
    no_media += 1

print("topic 覆盖:", dict(topic_kinds))
print("链接总数:", dict(link_kinds))
print("只有脚本没有媒体下载的 topic:", no_media)
print("媒体链接域名分布:", media_hosts.most_common(15))

print("\n样例（前 3 个 topic 的 script/media 链接）:")
for tid, title, links_json, _ in rows[:3]:
  links = json.loads(links_json)
  print(f"\n[{tid}] {title[:48]}")
  for l in links:
    if l["kind"] in ("script", "media"):
      print(f"  {l['kind']:7} {l['name'][:40]!r:44} {l['url'][:80]}")
