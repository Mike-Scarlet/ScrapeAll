import sqlite3, collections
con = sqlite3.connect(r"F:\Python\ScrapeAll\data\local_library.db")
con.row_factory = sqlite3.Row
for r in con.execute("SELECT creator, rel_path, original_name, parse_method, folder_date FROM LibraryFolder LIMIT 6"):
    print(dict(r))
print("...")
pref = collections.Counter()
for r in con.execute("SELECT rel_path FROM LibraryFolder"):
    p = r["rel_path"] or ""
    pref[p.replace("\\", "/").split("/")[0]] += 1
print(dict(pref))
con.close()
