# 一次性（只读）：407591 行现状态 + 330402 帖 stat + 目标夹现存文件
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
con = sqlite3.connect(os.path.join(ROOT, "data", "eroscripts.db"))
try:
  print(con.execute(
      "select url, probe_status, dl_status, dl_retries, dl_note, dl_path "
      "from EroLink where url like '%v=407591'").fetchall())
  print("topic 330402:", con.execute(
      "select topic_id, stat from EroTopicItem where topic_id=330402").fetchall())
finally:
  con.close()
d = r"J:\es_scrape\330402"
if os.path.isdir(d):
  for f in os.listdir(d):
    p = os.path.join(d, f)
    print(f"{os.path.getsize(p):>12,}B  {f}")
else:
  print("dest 目录不存在:", d)
