import json, sqlite3
con = sqlite3.connect(r"F:\Python\ScrapeAll\data\cangku.db")
con.row_factory = sqlite3.Row
r = con.execute("SELECT url, links_json FROM PostItem WHERE url LIKE '%222356%'").fetchone()
links = json.loads(r["links_json"])
baidu = next(l for l in links if "pan.baidu.com" in l["url"])
print(baidu["url"], "| pwd:", baidu.get("pwd"))
con.close()
