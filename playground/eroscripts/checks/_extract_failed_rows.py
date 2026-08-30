# 只读：查 EroExtract 失败行 + 总量对账
import os
import sys

import sqlite3

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB = os.path.join(ROOT, "data", "eroscripts.db")
db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row
rows = db.execute("SELECT archive_path, status, depth, parent_path, note, extracted_at, files_json FROM EroExtract").fetchall()
from collections import Counter
print("status 分布:", dict(Counter(r["status"] for r in rows)))
print(f"\n失败行 {sum(1 for r in rows if r['status'] != 'done')}:")
for r in rows:
    if r["status"] != "done":
        print(f"  [{r['status']}] d{r['depth']}  {r['archive_path']}")
        print(f"         note: {r['note']}")
import json
print(f"\ndone 行 files_json 文件总数: {sum(len(json.loads(r['files_json'] or '[]')) for r in rows if r['status'] == 'done')}")
