import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
con = sqlite3.connect(Path(__file__).resolve().parents[1] / "data" / "cangku.db")
con.row_factory = sqlite3.Row
for r in con.execute("SELECT url, title, links_json FROM PostItem WHERE stat=2"):
    l = json.loads(r["links_json"])[0]
    if any(k in r["title"] for k in ("はれ", "topu", "ZHAO", "はれ")):
        print(r["title"][:45], "| box:", repr(l.get("box_title")))
# はれ 是否在本地库
con2 = sqlite3.connect(Path(__file__).resolve().parents[1] / "data" / "local_library.db")
names = [r[0] for r in con2.execute("SELECT creator FROM LibraryFolder")]
print("本地库有 はれ:", "はれ" in names, "| harechippai:", "harechippai" in [n.casefold() for n in names])
