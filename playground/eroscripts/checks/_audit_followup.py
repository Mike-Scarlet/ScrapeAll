# 只读：追查对账发现的 3 个疑点的库侧证据（331228 gofile 目录行 / 3 组同名互撞行的
# dl_note 与时间线）。mode=ro。
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
db = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'eroscripts.db')}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

print("=== 331228 帖全部链接行 ===")
for r in db.execute("SELECT url, host, kind, probe_status, dl_status, dl_path, dl_size, dl_note, dl_at FROM EroLink WHERE first_topic_id=331228"):
    print(dict(r))

print("\n=== 同名互撞 3 组的时间线 ===")
for pat in (
    ("314297", "%rj01583098%", ),
    ("329965", "%hololive-vtuber-amane-kanata%"),
    ("324422", "%Loli God Requiem%"),
):
    tid, like = pat
    print(f"--- topic {tid} ---")
    for r in db.execute(
        "SELECT url, dl_size, dl_at, dl_note FROM EroLink WHERE dl_path LIKE ? ORDER BY dl_at", (like,)
    ):
        print(f"  dl_at={r['dl_at']}  size={r['dl_size']}  {r['url']}")
        if r["dl_note"]:
            print(f"    note: {r['dl_note']}")
