
import os, sqlite3

con = sqlite3.connect("data/eroscripts.db")
rows = con.execute(
    "SELECT url, probe_status, dl_status, dl_size, dl_path, dl_note "
    "FROM EroLink WHERE host='files.catbox.moe'").fetchall()
print(f"catbox 链接共 {len(rows)} 条：")
for url, p, d, size, path, note in rows:
    print(f"  {p}/{d} size={size or 0} path={path or '-'}")
    print(f"    note={note or ''} url={url}")
    if path:
        full = os.path.join(r"J:\es_scrape", path)
        ok = os.path.exists(full)
        actual = os.path.getsize(full) if ok else -1
        print(f"    J盘实况: exists={ok} 实际 {actual}B (库记 {size or 0}B)"
              f"{'  <-- 对不上!' if ok and size and actual != size else ''}")
con.close()

print("\n-- topic 310118 目录：")
d = r"J:\es_scrape\310118"
print("  不存在" if not os.path.isdir(d) else "\n".join(
    f"  {f}  {os.path.getsize(os.path.join(d, f))}B" for f in os.listdir(d)))

print("\n-- Temp 残留 crdownload：")
tmp = os.environ.get("LOCALAPPDATA", "") + r"\Temp"
for root, dirs, files in os.walk(tmp):
    if "playwright-artifacts" in root:
        for f in files:
            if f.endswith((".crdownload", ".part")):
                p = os.path.join(root, f)
                print(f"  {p}  {os.path.getsize(p)}B")
