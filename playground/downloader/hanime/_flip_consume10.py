# 一次性：consume-10 验证选中的 10 帖 stat 3->2（续吃语义：让 pending 链接
# 重新可见，跑完后 pass 会自动推回 3）
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = os.path.join(ROOT, "data", "eroscripts.db")
IDS = [307860, 307861, 308204, 308211, 308264, 308303, 308406, 308831,
       308887, 311626, 311783, 312344, 313351, 313439, 313545, 314235,
       315046, 315416, 316059, 316555, 316572, 316573, 316574, 316575,
       316576, 316577, 316732, 316971, 317223, 317414]

con = sqlite3.connect(DB)
try:
  marks = ",".join("?" for _ in IDS)
  before = con.execute(
      f"SELECT topic_id, stat FROM EroTopicItem WHERE topic_id IN ({marks})",
      IDS).fetchall()
  print(f"翻前: {before}")
  cur = con.execute(
      f"UPDATE EroTopicItem SET stat=2 WHERE topic_id IN ({marks}) AND stat=3",
      IDS)
  con.commit()
  print(f"UPDATE 影响行数: {cur.rowcount}")
  after = con.execute(
      f"SELECT topic_id, stat FROM EroTopicItem WHERE topic_id IN ({marks})",
      IDS).fetchall()
  print(f"翻后: {after}")
finally:
  con.close()
