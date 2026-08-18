import json, re, sqlite3

con = sqlite3.connect(r"F:\Python\ScrapeAll\data\local_library.db")
local_creators = [r[0] for r in con.execute("SELECT creator FROM LibraryFolder")]
con.close()

con = sqlite3.connect(r"F:\Python\ScrapeAll\data\cangku.db")
con.row_factory = sqlite3.Row
rows = con.execute("SELECT url, title, links_json FROM PostItem WHERE stat=2").fetchall()
con.close()

def fold(s):
    """宽松键：casefold + 去掉非字母数字（抓 CunnyFunk/CunnyFunky、CBX-CJW 类差异做人工参考）"""
    return re.sub(r"[^a-z0-9\u3040-\u30ff\u4e00-\u9fff]", "", (s or "").casefold())

local_fold = {fold(c): c for c in local_creators}

# 全量报告（35 链接那轮）里被判"本地库无记录"的作者，配上帖子信息
NEW_FROM_REPORT = {
    "Dim": "228416", "NFFA": "227486", "Mimu": "225896",
    "Yakin": "225885", "Solis": "225540", "CunnyFunky": "225124",
}
# 山含 225111 是死链，walk 不到，单独列

posts = {}
for r in rows:
    pid = r["url"].rstrip("/").split("/")[-1]
    links = json.loads(r["links_json"] or "[]")
    baidu = next((l for l in links if "pan.baidu.com" in (l.get("url") or "")), None)
    posts[pid] = (r["title"], (baidu or {}).get("box_title") or "")

for name, pid in NEW_FROM_REPORT.items():
    title, box = posts.get(pid, ("?", "?"))
    hits = [v for k, v in local_fold.items() if fold(name) and fold(name) in k or k and k in fold(name)]
    exact = fold(name) in local_fold
    print(f"作者目录 {name!r}  post {pid}  box_title {box!r}")
    print(f"    title: {title}")
    print(f"    宽松名相似: {sorted(set(hits)) if hits else '无'}"
          f"{'（exact）' if exact else ''}")
print()
pid = "225111"
title, box = posts.get(pid, ("?", "?"))
print(f"死链 post {pid} 山含: title={title!r} box_title={box!r}")
print(f"    宽松名相似: {sorted({v for k, v in local_fold.items() if fold('山含') and (fold('山含') in k or k in fold('山含'))}) or '无'}")
print()
print("本地库全部 46 作者（供对照）:")
print("  " + " ".join(sorted(local_creators)))
