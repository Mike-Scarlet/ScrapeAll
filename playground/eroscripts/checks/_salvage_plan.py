# 只读：生成 3 个被覆盖件的人工回捞清单——下载 URL、目标落盘路径（对齐引擎
# 撞名规则 {stem}.{url_token}{ext}）、期望字节数、现有文件参照。
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from scrape_all.downloader.fsutil import url_token

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEST = r"J:\es_scrape"

URLS = [
    ("https://discuss.eroscripts.com/uploads/short-url/wjGqH830ZT3FaBay8vC5n5P2b9B.funscript", 82316),
    ("https://discuss.eroscripts.com/uploads/short-url/es72xGEyMNUGmoOs8njocE3RShu.funscript", 136766),
    ("https://pixeldrain.com/l/bAjwCZDy", 299620706),
]

db = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'eroscripts.db')}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

for url, expect in URLS:
    r = db.execute("SELECT first_topic_id, dl_path, dl_size, dl_at FROM EroLink WHERE url=?", (url,)).fetchone()
    rel = r["dl_path"]
    stem, ext = os.path.splitext(rel)
    tok = url_token(url)
    target = f"{stem}.{tok}{ext}"
    disk = os.path.join(DEST, rel.replace("/", os.sep))
    print(f"URL:     {url}")
    print(f"期望体积: {expect}B（库内记录）")
    print(f"现有文件: {rel}")
    print(f"  盘上实存: {os.path.exists(disk)}  实际体积: {os.path.getsize(disk) if os.path.exists(disk) else '-'}B（这是覆盖者的，保留不动）")
    print(f"放到:    {target}")
    print(f"  完整路径: {os.path.join(DEST, target.replace('/', os.sep))}")
    print()
