# 一次性：407591 行复位（exhausted 是 adapter bug 烧完的额度，非站点问题，
# 连 retries 一并清零）+ 330402 帖 stat 3->2 待 consume 重收
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
con = sqlite3.connect(os.path.join(ROOT, "data", "eroscripts.db"))
try:
  print("复位前:", con.execute(
      "select dl_status, dl_retries from EroLink where url=?",
      ("https://hanime1.me/download?v=407591",)).fetchall())
  con.execute(
      "update EroLink set dl_status='pending', dl_note='', dl_path='', dl_retries=0 "
      "where url=?", ("https://hanime1.me/download?v=407591",))
  cur = con.execute(
      "update EroTopicItem set stat=2 where topic_id=330402 and stat=3")
  con.commit()
  print(f"复位后: {con.execute('select dl_status, dl_retries from EroLink where url=?', ('https://hanime1.me/download?v=407591',)).fetchall()}; topic UPDATE {cur.rowcount}")
finally:
  con.close()
