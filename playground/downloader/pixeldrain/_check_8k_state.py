
"""查 8K 版 dXLrSpoR 的当前库内状态 + 313014 落盘目录。只读。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

with TopicStore(os.path.join(_ROOT, "data", "eroscripts.db")) as store:
  for url in ("https://pixeldrain.com/d/dXLrSpoR", "https://pixeldrain.com/d/WTYzy3Wo"):
    r = store.db.QueryOne(EroLink, where="url = ?", params=(url,))
    if r is None:
        print(url, "-> 无记录")
        continue
    print(f"{url}\n  dl={r.dl_status} retries={r.dl_retries} probe={r.probe_status} "
          f"path={r.dl_path or '-'} size={r.dl_size}\n  note: {r.dl_note}")

d = r"J:\es_scrape\313014"
if os.path.isdir(d):
  for f in sorted(os.listdir(d)):
    p = os.path.join(d, f)
    print(f"  盘面: {os.path.getsize(p):>12,}  {f}")
else:
  print("盘面: 313014 目录不存在")
