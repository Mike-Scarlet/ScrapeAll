# 改库：三个被覆盖件的人工回捞落账——dl_path 指到 token 第二把、dl_at 刷新、
# dl_note 记回捞标记。写前逐行打印现值，写后复核。busy_timeout=30s 避让并发 agent。
import os
import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB = os.path.join(ROOT, "data", "eroscripts.db")

UPDATES = [
    ("https://discuss.eroscripts.com/uploads/short-url/wjGqH830ZT3FaBay8vC5n5P2b9B.funscript",
     r"314297\[Sanjiku] RJ01583098 - The Slutty Young Lady Is Restrained And Taught A Lesson ~Her Pride Is Shattered~ (Part.3d00110b.funscript",
     82316),
    ("https://discuss.eroscripts.com/uploads/short-url/es72xGEyMNUGmoOs8njocE3RShu.funscript",
     r"329965\hololive-vtuber-amane-kanata-and-i-have-sex-in-a-secret-room_720p.b540bead.funscript",
     136766),
    ("https://pixeldrain.com/l/bAjwCZDy",
     r"324422\[貧乳愛好会会長補佐代理見習い] Loli God Requiem.499e0052.zip",
     299620706),
]

db = sqlite3.connect(DB, timeout=30)
db.row_factory = sqlite3.Row
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
note = "人工回捞被覆盖件（同名互撞丢内容，token 第二把复位）"

for url, rel, size in UPDATES:
    row = db.execute("SELECT dl_status, dl_path, dl_size, dl_at FROM EroLink WHERE url=?",
                     (url,)).fetchone()
    if row is None:
        print(f"[缺行] {url}")
        sys.exit(1)
    print(f"{url}")
    print(f"  旧: status={row['dl_status']} path={row['dl_path']} size={row['dl_size']} at={row['dl_at']}")
    db.execute(
        "UPDATE EroLink SET dl_path=?, dl_size=?, dl_at=?, dl_note=? WHERE url=?",
        (rel, size, now, note, url))
    print(f"  新: status=downloaded path={rel} size={size} at={now}")

db.commit()
print("\n--- 写后复核 ---")
for url, rel, size in UPDATES:
    row = db.execute("SELECT dl_status, dl_path, dl_size FROM EroLink WHERE url=?", (url,)).fetchone()
    match = row["dl_path"] == rel and row["dl_size"] == size and row["dl_status"] == "downloaded"
    print(f"  {'OK' if match else '[不符]'}  {row['dl_status']}  {row['dl_path']}  {row['dl_size']}B")
db.close()
