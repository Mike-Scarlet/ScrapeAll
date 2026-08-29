import sqlite3

db = sqlite3.connect("data/eroscripts.db")
n, = db.execute("select count(*) from EroTopicItem").fetchone()
mn, mx = db.execute("select min(bumped_at), max(bumped_at) from EroTopicItem").fetchone()
nololi = db.execute(
    "select count(*) from EroTopicItem where tags_json not like '%loli%'").fetchone()[0]
print(f"topics={n} bumped range: {mn} .. {mx}  无loli标签: {nololi}")
print("stat分布:", db.execute(
    "select stat, count(*) from EroTopicItem group by stat").fetchall())
for r in db.execute("select topic_id, author, substr(title,1,38), bumped_at, posts_count "
                    "from EroTopicItem order by bumped_at desc limit 3"):
  print(" ", r)
print("flags:", db.execute("select key, value from ScrapeMeta").fetchall())
