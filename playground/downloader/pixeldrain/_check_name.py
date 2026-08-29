
"""核对 QJSXZzdn 的页面显示名 vs 已落盘文件名（1 次页面加载，0 下载）"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.downloader.adapters import adapter_for
from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

_VERIFY = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                       "data", "eroscripts", "files", "_verify")


async def main():
  adapter = adapter_for("https://pixeldrain.com/u/x")
  async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
    p = await adapter.probe(engine, "https://pixeldrain.com/u/QJSXZzdn")
    print(f"页面 probe: name={p.filename!r} size={p.size} note={p.note}")
    print(f"磁盘文件 : {[f for f in os.listdir(_VERIFY) if 'P5' in f or 'Wardens' in f]}")
    # 幂等视角：title 名 sanitize 后磁盘上是否存在（存在 => 下次不会再点按钮）
    from scrape_all.downloader.fsutil import sanitize_filename
    local = sanitize_filename(p.filename or "")
    print(f"title 推导幂等名: {local!r} -> 磁盘存在={os.path.exists(os.path.join(_VERIFY, local))}")


asyncio.run(main())
