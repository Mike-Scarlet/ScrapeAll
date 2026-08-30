
"""四件 canceled 大件 + AV1 对照的库内状态与盘面残留。只读。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

URLS = [
    "https://pixeldrain.com/d/dXLrSpoR",   # 8K 3.57G（用户取消，已 skipped）
    "https://pixeldrain.com/d/LU2c18fN",   # 2.86G
    "https://pixeldrain.com/d/YQ7aqfSd",   # 2.77G
    "https://pixeldrain.com/d/62QyVqgs",   # 2.21G
    "https://pixeldrain.com/d/6CkkK4Aj",   # 1.09G AV1（对照：应 downloaded）
]

with TopicStore(os.path.join(_ROOT, "data", "eroscripts.db")) as store:
  for u in URLS:
    r = store.db.QueryOne(EroLink, where="url = ?", params=(u,))
    print(f"{u}\n  dl={r.dl_status} retries={r.dl_retries} path={r.dl_path or '-'} "
          f"size={r.dl_size}\n  note: {r.dl_note}")

for tid in ("319262", "331305"):
  d = os.path.join(r"J:\es_scrape", tid)
  print(f"盘面 {d}:")
  if os.path.isdir(d):
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        print(f"  {os.path.getsize(p):>13,}  {f}")
  else:
    print("  目录不存在")
