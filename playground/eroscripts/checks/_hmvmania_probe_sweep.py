"""存量 8 条 hmvmania EroLink 全量 probe（0 正文流量），确认整族形态供放量决策"""
import asyncio
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.downloader.adapters import adapter_for
from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_CONCURRENCY, DOWNLOADER_PROXY_SERVER


def fmt(n):
    return f"{n / 1024 / 1024:.1f}MB" if n and n >= 1024 * 1024 else f"{n}B" if n else "?"


async def main():
    con = sqlite3.connect("data/eroscripts.db")
    urls = [r[0] for r in con.execute(
        "SELECT url FROM EroLink WHERE url LIKE '%hmvmania.com/video/%' ORDER BY url")]
    con.close()
    print(f"{len(urls)} 条")
    from collections import Counter
    stat = Counter()
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER, DOWNLOADER_CONCURRENCY) as engine:
        adapter = adapter_for(urls[0])
        for u in urls:
            p = await adapter.probe(engine, u)
            stat[p.status] += 1
            print(f"  {p.status:8} {fmt(p.size):>9} {p.filename} | {p.note[:90]}")
    print("汇总:", dict(stat))

asyncio.run(main())
