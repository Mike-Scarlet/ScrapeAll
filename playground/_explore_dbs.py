"""探索两个库的数据现状：local_library.db（已抓日期） + cangku.db（仓库解析出的分享链接）。

只读，不碰浏览器。
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DATA = Path(__file__).resolve().parents[1] / "data"


def dump_local_library():
    print("=" * 70)
    print("local_library.db / library_folder")
    print("=" * 70)
    con = sqlite3.connect(DATA / "local_library.db")
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM LibraryFolder").fetchall()
    print("rows:", len(rows))
    for r in rows:
        d = dict(r)
        months = json.loads(d.pop("content_json") or "{}").get("downloaded_months")
        print(f"{d['folder_key']:24} date={d['folder_date']:8} method={d['parse_method']:12} "
              f"rel_path={d['rel_path']}  original={d['original_name']!r}")
        print(f"{'':24} months({len(months) if months else 0}): {months}")
    con.close()


def dump_cangku_links():
    print()
    print("=" * 70)
    print("cangku.db / post_item（只看 stat 和 links）")
    print("=" * 70)
    con = sqlite3.connect(DATA / "cangku.db")
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT * FROM PostItem").fetchall()
    except sqlite3.OperationalError as e:
        print("table err:", e)
        print([r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")])
        return
    stat_count = {}
    link_rows = []
    for r in rows:
        d = dict(r)
        stat_count[d["stat"]] = stat_count.get(d["stat"], 0) + 1
        if d["links_json"]:
            link_rows.append(d)
    print("stat 分布:", stat_count)
    print("带 links 的帖:", len(link_rows))
    for d in link_rows[:40]:
        links = json.loads(d["links_json"])
        print(f"  id={d['url'].rstrip('/').split('/')[-1]:>8} stat={d['stat']} links={len(links)}  {d['title'][:40]!r}")
        for lk in links[:6]:
            print(f"      {lk}")
    con.close()


if __name__ == "__main__":
    dump_local_library()
    dump_cangku_links()
