# 只读实验：档案的 topic 分布（一个 topic 多包是否存在 → 解压目录碰撞策略依据）
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEST = r"J:\es_scrape"
topic_archives = Counter()
topic_loose = Counter()
for dirpath, _dn, filenames in os.walk(DEST):
    topic = os.path.basename(dirpath)
    for fn in filenames:
        if os.path.splitext(fn)[1].lower() in {".zip", ".rar", ".7z"}:
            topic_archives[topic] += 1
        else:
            topic_loose[topic] += 1
multi = {t: n for t, n in topic_archives.items() if n > 1}
print(f"有档案的 topic: {len(topic_archives)} 个 / 档案总数 {sum(topic_archives.values())}")
print(f"一个 topic 多包: {len(multi)} 个 {dict(multi)}")
both = [t for t in topic_archives if topic_loose.get(t, 0) > 0]
print(f"包与散文件同夹的 topic: {len(both)} 个（示例 {both[:8]}）")
