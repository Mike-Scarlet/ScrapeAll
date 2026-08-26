
"""只读：links_json 真实字段结构 + stat=4/5 样例。"""
import json
import sqlite3

con = sqlite3.connect("data/eroscripts.db")
row = con.execute(
    "select links_json from EroTopicItem where stat=2 and links_json is not null limit 1"
).fetchone()
print("links_json[0..3]:")
for l in json.loads(row[0])[:3]:
    print(" ", l)

print("\nstat=4 样例 topic_id:", [r[0] for r in con.execute(
    "select topic_id from EroTopicItem where stat=4 limit 5")])
print("stat=5 样例 topic_id:", [r[0] for r in con.execute(
    "select topic_id from EroTopicItem where stat=5 limit 5")])
print("\nstat=4 是否有 links:", con.execute(
    "select count(*) from EroTopicItem where stat=4 and links_json is not null").fetchone())
print("stat=5 是否有 links:", con.execute(
    "select count(*) from EroTopicItem where stat=5 and links_json is not null").fetchone())
con.close()
