# 只读：J:\es_scrape 实盘文件扩展名/体积分布快照（决定配对脚本的 视频扩展名集合、
# zip/orphan 判定基础）。不写库不动盘。
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = r"J:\es_scrape"
ext_count = Counter()
ext_bytes = Counter()
partial = []          # .crdownload / .tmp 在途
dirs = 0
files = 0
total = 0
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirs += 1
    for fn in filenames:
        p = os.path.join(dirpath, fn)
        try:
            sz = os.path.getsize(p)
        except OSError:
            sz = 0
        files += 1
        total += sz
        ext = os.path.splitext(fn)[1].lower() or "(无扩展名)"
        ext_count[ext] += 1
        ext_bytes[ext] += sz
        if fn.endswith((".crdownload", ".tmp", ".part")):
            partial.append(p)

print(f"目录 {dirs} / 文件 {files} / 合计 {total/1024/1024/1024:.2f}GB")
print("\n=== 扩展名 x 数量 x 体积 Top 30 ===")
for ext, c in ext_count.most_common(30):
    print(f"{ext:14} {c:5}  {ext_bytes[ext]/1024/1024:12.1f}MB")
print(f"\n在途分片/临时文件: {len(partial)}")
for p in partial[:10]:
    print(" ", p)
