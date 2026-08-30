# 复跑判定：对单条 pixeldrain 链接用管线同款 adapter.probe() 重新探活（只读探测，不下载）
# 用法：python playground/eroscripts/checks/_probe_one_pd.py https://pixeldrain.com/d/E1Kk51Ls
import os
import sys
import asyncio
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from config import DOWNLOADER_PROXY_SERVER
from scrape_all.downloader.engine import DownloadEngine
from scrape_all.downloader.adapters import adapter_for
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
DB = os.path.join(DB, "data", "eroscripts.db")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ap = argparse.ArgumentParser()
ap.add_argument("url")
args = ap.parse_args()

with TopicStore(DB) as store:
    rows = store.db.QueryRecords(EroLink, where="url = ?", params=[args.url])
    for r in rows:
        print(f"库内现状: probe_status={r.probe_status} retries={r.probe_retries} "
              f"dl_status={r.dl_status} dl_note={r.dl_note!r} host={r.host} kind={r.kind}")
        print(f"  first_topic_id={r.first_topic_id} meta={r.meta_json!r}")

async def main():
    a = adapter_for(args.url)
    print(f"\nadapter: {a.__class__.__name__}  现跑 probe ...")
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        r = await a.probe(engine, args.url)
    print(f"probe 结果: status={r.status} filename={r.filename!r} "
          f"size={r.size} note={r.note!r}")

asyncio.run(main())
