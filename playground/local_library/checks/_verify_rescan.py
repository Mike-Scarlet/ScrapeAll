"""对比备份库与重扫库：月份集合零回归 + 全部换成 month->路径 新格式。"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data")


def load(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    out = {}
    for r in con.execute(
        "SELECT folder_key, creator, rel_path, folder_date, parse_method, content_json FROM LibraryFolder"):
        v = json.loads(r["content_json"] or "{}").get("downloaded_months")
        row = dict(r)
        row["months"] = set(v) if isinstance(v, dict) else set(v or [])
        row["is_dict"] = isinstance(v, dict)
        out[r["folder_key"]] = row
    con.close()
    return out


old = load(os.path.join(DATA, "local_library.db.bak-20260818"))
new = load(os.path.join(DATA, "local_library.db"))

print(f"rows: old={len(old)} new={len(new)}  key差异: {set(old) ^ set(new) or '无'}")
diff = {k for k in old if old[k]["months"] != new.get(k, {}).get("months")}
print(f"月份集合有差异的作者: {sorted(diff) or '无（零回归）'}")
changed = [k for k in old
           if (new[k]["rel_path"], new[k]["parse_method"], new[k]["folder_date"])
           != (old[k]["rel_path"], old[k]["parse_method"], old[k]["folder_date"])]
print(f"rel_path/parse_method/folder_date 变动: {changed or '无'}")

bad = [k for k, v in new.items() if not v["is_dict"]]
print(f"仍是旧 list 格式: {bad or '无'}")
empty = [k for k, v in new.items() if not all(v["months"])]
print(f"月份集合为空的作者: {empty or '无'}")
total = sum(len(p) for v in new.values() for p in json.loads(v["content_json"])["downloaded_months"].values())
print(f"索引路径总条数: {total}")
sample = next(iter(new.values()))
print(f"样例 {sample['folder_key']}: {json.loads(sample['content_json'])['downloaded_months']}")
