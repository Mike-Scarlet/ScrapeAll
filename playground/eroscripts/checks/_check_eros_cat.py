
import json
import sqlite3

db = sqlite3.connect("data/eroscripts.db")
print("category 分布:", db.execute(
    "select category_id, count(*) from EroTopicItem group by category_id order by 2 desc"
).fetchall())
print("cat14 样例:")
for r in db.execute(
    "select topic_id, url, substr(title,1,50), posts_count, views "
    "from EroTopicItem where category_id=14 order by bumped_at desc limit 8"):
  print(" ", r)
print("cat14 帖子总数:", db.execute(
    "select sum(posts_count) from EroTopicItem where category_id=14").fetchone())
