# 只读实验：最新落盘的档案（确认 102→103 是否在途新增）
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEST = r"J:\es_scrape"
hits = []
for dirpath, _dn, filenames in os.walk(DEST):
    for fn in filenames:
        if os.path.splitext(fn)[1].lower() in {".zip", ".rar", ".7z"}:
            p = os.path.join(dirpath, fn)
            hits.append((os.path.getmtime(p), p))
hits.sort(reverse=True)
now = time.time()
print(f"档案总数 {len(hits)}")
for mt, p in hits[:6]:
    print(f"{(now - mt) / 60:8.1f}min ago  {os.path.relpath(p, DEST)}")
