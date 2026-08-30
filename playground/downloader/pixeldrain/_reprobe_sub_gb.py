
"""翻 GB 以下 /d 待捞链接的存活状态：直接重探 + mark_probe 落库。

alive -> dl 不动（留在待捞队列）；dead -> dl dead（终态出队）；
unknown -> 留给正式编排器在 consume_link 里二次探。
"""
import asyncio
import json
import os
import re
import sys
from collections import Counter
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from config import DOWNLOADER_PROXY_SERVER
from scrape_all.downloader.engine import DownloadEngine
from scrape_all.downloader.adapters import adapter_for
from scrape_all.sites.eroscripts.consume import fmt_size
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink

GB = 1024 ** 3

with TopicStore(os.path.join("data", "eroscripts.db")) as store:
  rows = store.db.QueryRecords(EroLink, where="host = ?", params=["pixeldrain.com"])
  targets = []
  for r in rows:
    if not urlsplit(r.url).path.startswith("/d/") or r.dl_status != "pending":
        continue
    try:
        size = json.loads(r.meta_json or "{}").get("size") or 0
    except ValueError:
        size = 0
    if size < GB:
        targets.append((size, r))
  targets.sort(key=lambda t: t[0])
  print(f"GB 以下待捞 {len(targets)} 条，重探中：")


  async def main():
    adapter = adapter_for("https://pixeldrain.com/d/x")
    stat = Counter()
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
      for i, (size, row) in enumerate(targets, 1):
        try:
            p = await adapter.probe(engine, row.url)
            meta = {k: v for k, v in (("filename", p.filename), ("size", p.size))
                    if v} or None
            store.mark_probe(row.url, p.status, meta=meta, note=p.note)
        except Exception as e:
            note = f"{type(e).__name__}: {e}"
            store.mark_probe(row.url, "unknown", note=note)
            p = type("P", (), {"status": "unknown", "note": note, "size": None})()
        stat[p.status] += 1
        print(f"  [{i:>2}/{len(targets)}] {p.status:7s} {fmt_size(p.size)}  {row.url}")
        await asyncio.sleep(0.5)
    print(f"\n重探汇总: {dict(stat)}")


  asyncio.run(main())
