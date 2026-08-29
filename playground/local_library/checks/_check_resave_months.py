import json, sqlite3
con = sqlite3.connect(r"F:\Python\ScrapeAll\data\local_library.db")
con.row_factory = sqlite3.Row
want = [("CBX-CJW", "2025.10"), ("neNeG", "2025.07"), ("煌めく星", "2025.08"),
        ("sydusarts", "2025.09"), ("Mokusheep", "2025.10"),
        ("Erio", "2025.08"), ("ink+", "2025.11"), ("AS109", "2025.11")]
for creator, mo in want:
    r = con.execute("SELECT creator, content_json FROM LibraryFolder WHERE creator=?", (creator,)).fetchone()
    data = json.loads(r["content_json"])["downloaded_months"]
    paths = data.get(mo) or []
    print(f"{creator} {mo}: {len(paths)} 条")
    for p in paths[:15]:
        print(f"    {p}")
    if len(paths) > 15:
        print(f"    ... 共 {len(paths)}")
    print()
con.close()
