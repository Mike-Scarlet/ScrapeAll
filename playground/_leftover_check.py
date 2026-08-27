
import re, sqlite3

rep = open("data/eroscripts/consume_report.txt", encoding="utf-8").read()
topics = re.findall(r"^=== topic (\d+)", rep, re.M)
closed = set(re.findall(r"^topic (\d+) -> CONSUMED", rep, re.M))
left = [t for t in topics if t not in closed]
print("本批登记过但未收口:", left or "无")
con = sqlite3.connect("data/eroscripts.db")
for t in left:
    rows = con.execute(
        "SELECT url, probe_status, dl_status, dl_note FROM EroLink WHERE first_topic_id=?",
        (t,)).fetchall()
    for u, p, d, n in rows:
        if d not in ("downloaded", "skipped", "dead", "manual", "exhausted"):
            print(f"  {p}/{d} {n or ''} {u}")
con.close()
