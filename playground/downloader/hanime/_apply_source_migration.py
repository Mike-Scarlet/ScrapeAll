# 一次性迁移（已批准）：该站 EroLink 存量 80 条 source/skipped -> pending，
# 让 consume 流水能吃。只动 host=hanime1.me、skipped、视频页形态
# （/watch?v= / /download?v= / watch?...&v= 三种），镜像 host 与 other 不碰。
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = os.path.join(ROOT, "data", "eroscripts.db")

WHERE = ("host='hanime1.me' AND dl_status='skipped' "
         "AND (url LIKE '%/watch?v=%' OR url LIKE '%/download?v=%' "
         "OR url LIKE '%/watch?%v=%')")

con = sqlite3.connect(DB)
try:
  before = con.execute(
      "SELECT dl_status, COUNT(*) FROM EroLink "
      "WHERE host='hanime1.me' GROUP BY dl_status").fetchall()
  print(f"迁移前: {before}")
  cur = con.execute(
      "UPDATE EroLink SET dl_status='pending', dl_note='' WHERE " + WHERE)
  con.commit()
  print(f"UPDATE 影响行数: {cur.rowcount}")
  after = con.execute(
      "SELECT dl_status, COUNT(*) FROM EroLink "
      "WHERE host='hanime1.me' GROUP BY dl_status").fetchall()
  print(f"迁移后: {after}")
  left = con.execute(
      "SELECT COUNT(*) FROM EroLink WHERE " + WHERE).fetchone()[0]
  print(f"谓词下剩余可迁移行: {left}")
  mirrors = con.execute(
      "SELECT host, dl_status, COUNT(*) FROM EroLink "
      "WHERE host LIKE '%hanime%' AND host != 'hanime1.me' "
      "GROUP BY host, dl_status").fetchall()
  print(f"镜像/旁系（应原样不动）: {mirrors}")
finally:
  con.close()
