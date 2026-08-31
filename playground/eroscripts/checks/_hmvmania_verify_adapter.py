"""hmvmania adapter 真链接验证：321390 (CC005 Beethoven) probe + download + 幂等复跑"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.downloader.adapters import adapter_for
from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_CONCURRENCY, DOWNLOADER_PROXY_SERVER

URL = ("https://hmvmania.com/video/hmvhero69-cc005-beethoven-legend-clover/"
       "#/?playlistId=0&videoId=0")
DEST = os.path.join("data", "eroscripts", "files", "_verify")


def fmt(n):
    return f"{n / 1024 / 1024:.1f}MB" if n and n >= 1024 * 1024 else f"{n}B"


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER, DOWNLOADER_CONCURRENCY) as engine:
        adapter = adapter_for(URL)
        print("adapter:", type(adapter).__name__)
        p = await adapter.probe(engine, URL)
        print(f"probe: {p.status} name={p.filename} size={fmt(p.size)}\n  note: {p.note}")
        assert p.status == "alive", "probe 未翻 alive"
        d = await adapter.download(engine, URL, DEST)
        print(f"download: {d.status} path={d.path} size={fmt(d.size)} note={d.note}")
        assert d.status == "downloaded", "下载未落盘"
        d2 = await adapter.download(engine, URL, DEST)
        print(f"re-download: {d2.status} path={d2.path} size={fmt(d2.size)} note={d2.note}")
        assert d2.status == "skipped", "幂等复跑未 skipped"
        print("OK: probe alive + downloaded + 幂等 skipped")

asyncio.run(main())
