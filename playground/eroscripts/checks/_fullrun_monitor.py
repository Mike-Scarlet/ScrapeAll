
import os, sqlite3, time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
_DB = os.path.join(_ROOT, "data", "eroscripts.db")
DST = r"J:\es_norm"

con = sqlite3.connect(_DB); con.row_factory = sqlite3.Row
rows = con.execute("SELECT status, action, COUNT(*) n FROM EroNorm "
                   "GROUP BY status, action ORDER BY status, action").fetchall()
print("-- EroNorm 状态分布")
for r in rows:
    print(f"  {r['status']:>8} / {r['action']:<10} : {r['n']}")
print(f"  总行数: {con.execute('SELECT COUNT(*) FROM EroNorm').fetchone()[0]}")
pend = con.execute(
    "SELECT topic_id, target_path, action FROM EroNorm "
    "WHERE status='failed' ORDER BY topic_id").fetchall()
if pend:
    print("-- failed 明细（前 20）")
    for r in pend[:20]:
        print(f"  {r['topic_id']}  {r['target_path']}  [{r['action']}]")
con.close()

n_files = n_dirs = 0
newest = []
for dirpath, dirnames, filenames in os.walk(DST):
    n_dirs += len(dirnames)
    for fn in filenames:
        n_files += 1
        p = os.path.join(dirpath, fn)
        try:
            st = os.stat(p)
            newest.append((st.st_mtime, st.st_size, p))
        except OSError:
            pass
newest.sort(reverse=True)
print(f"-- J:\\es_norm 盘面：{n_dirs} 目录 / {n_files} 文件")
print("  最近落盘 5 个：")
for mt, sz, p in newest[:5]:
    print(f"    {time.strftime('%H:%M:%S', time.localtime(mt))}  "
          f"{sz/2**20:9.1f}MB  {p[len(DST)+1:]}")
