
import sqlite3

con = sqlite3.connect("data/eroscripts.db")
row = con.execute(
    "SELECT probe_status, dl_status, probe_retries, dl_retries, meta_json, dl_at "
    "FROM EroLink WHERE url='https://files.catbox.moe/9p4z2f.mp4'").fetchone()
print("probe/dl:", row[0], "/", row[1], " probe_retries:", row[2], " dl_retries:", row[3])
print("meta:", row[4])
print("dl_at:", row[5])
con.close()
