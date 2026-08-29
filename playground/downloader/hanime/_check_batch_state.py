# 一次性（只读）：批跑期间看该站非终态残留 + 42 帖 stat
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DB = os.path.join(ROOT, "data", "eroscripts.db")
IDS = [317534, 317910, 317917, 318538, 318615, 319393, 319919, 319924,
       320322, 320750, 321139, 321303, 321523, 321832, 322474, 322866,
       323014, 323134, 323226, 323443, 323951, 324108, 324272, 325044,
       325120, 325177, 326544, 326572, 326892, 326958, 326973, 327729,
       327872, 327888, 328020, 328021, 329355, 329363, 330402, 331228,
       331754, 332226]

con = sqlite3.connect(DB)
try:
  rows = con.execute(
      "select url, dl_status, dl_note from EroLink "
      "where host='hanime1.me' and dl_status not in "
      "('downloaded','skipped','dead','manual','exhausted')").fetchall()
  print(f"非终态残留: {len(rows)}")
  for r in rows:
    print(f"  {r[0]} {r[1]} {r[2]}")
  marks = ",".join("?" for _ in IDS)
  stats = con.execute(
      f"select stat, count(*) from EroTopicItem where topic_id in ({marks}) "
      "group by stat", IDS).fetchall()
  print(f"42 帖 stat 分布: {stats}")
finally:
  con.close()
