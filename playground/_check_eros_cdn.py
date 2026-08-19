
import json
import sqlite3
from collections import Counter
from urllib.parse import urlsplit

db = sqlite3.connect("data/eroscripts.db")
rows = db.execute("select topic_id, links_json from EroTopicItem where stat=2").fetchall()

cdn = Counter()
cdn_ext = Counter()
samples = []
for tid, links_json in rows:
  for l in json.loads(links_json) if links_json else []:
    u = l["url"]
    if "eroscripts.com" in urlsplit(u).netloc:
      cdn[urlsplit(u).netloc] += 1
      cdn_ext[urlsplit(u).path.rsplit(".", 1)[-1] if "." in urlsplit(u).path else "-"] += 1
      if len(samples) < 8:
        samples.append((tid, l["kind"], l["name"][:36], u[:100]))

print("eroscripts 系域名链接分布:", dict(cdn))
print("路径扩展名分布:", cdn_ext.most_common())
print("\n样例:")
for s in samples:
  print(" ", s)
