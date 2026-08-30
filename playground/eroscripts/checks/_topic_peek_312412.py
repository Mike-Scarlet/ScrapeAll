# 只读：312412 全文过目找嵌套 rar 的密码线索
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
raw = json.load(open(os.path.join(ROOT, "data", "eroscripts", "topics", "312412.json"), encoding="utf-8"))
posts = ((raw.get("post_stream") or {}).get("posts")) or []
for i, post in enumerate(posts):
    text = re.sub(r"<br\s*/?>", "\n", post.get("cooked") or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    print(f"--- #{i} {post.get('username')} ---")
    print(text.strip()[:1200])
    print()
# links_json 也看看（parse 收了什么）
import sqlite3
db = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'eroscripts.db')}?mode=ro", uri=True)
db.row_factory = sqlite3.Row
row = db.execute("SELECT links_json FROM EroTopicItem WHERE topic_id=312412").fetchone()
print("links_json:", row["links_json"][:800] if row else None)
