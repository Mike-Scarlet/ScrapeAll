import json, sqlite3, sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "local_library.db")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute("SELECT * FROM LibraryFolder LIMIT 3").fetchall()
cols = rows[0].keys() if rows else []
print("columns:", list(cols))
print("count:", con.execute("SELECT COUNT(*) FROM LibraryFolder").fetchone()[0])
print()

# JSON 顶层 key 全库统计
key_stat = {}
path_like = {}
for r in con.execute("SELECT creator, content_json FROM LibraryFolder"):
    data = json.loads(r["content_json"] or "{}")
    for k, v in data.items():
        key_stat[k] = key_stat.get(k, 0) + 1
    for k, v in data.items():
        if isinstance(v, str) and ("/" in v or "\\" in v):
            path_like.setdefault(k, set()).add(v)
print("content_json 顶层 key 出现次数:", key_stat)
print()
for k, vals in path_like.items():
    print(f"key {k!r} 疑似路径 {len(vals)} 种，样例:")
    for v in sorted(vals)[:10]:
        print(f"    {v!r}")
print()

# 完整打印 2 条样例
for r in con.execute("SELECT creator, content_json FROM LibraryFolder LIMIT 2"):
    print("=" * 60)
    print("creator:", r["creator"])
    print(json.dumps(json.loads(r["content_json"]), ensure_ascii=False, indent=2)[:2000])
con.close()
