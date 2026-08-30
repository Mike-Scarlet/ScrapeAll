# 修复后单点验证（只读 probe，不下载）：新代码路径全形态过一遍
#   /d 新路径（两条曾误判 dead） /u 回归 /l 回归 /u 真死 /d 形态真死
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from config import DOWNLOADER_PROXY_SERVER
from scrape_all.downloader.engine import DownloadEngine
from scrape_all.downloader.adapters.pixeldrain import PixeldrainAdapter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CASES = [
    "https://pixeldrain.com/d/E1Kk51Ls",   # 曾误判 dead，实为 /d 独占页
    "https://pixeldrain.com/d/yZFyovdG",   # 同上
    "https://pixeldrain.com/u/PV82t9fy",   # /u 回归（已下载过的正常文件）
    "https://pixeldrain.com/l/o7yp2SFF",   # /l 列表回归
    "https://pixeldrain.com/u/6Mq5Lr2Q",   # 真死（双形态 404）
    "https://pixeldrain.com/d/6Mq5Lr2Q",   # 真死 id 的 /d 形态（合成用例）
]


async def main():
    a = PixeldrainAdapter()
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        for url in CASES:
            r = await a.probe(engine, url)
            print(f"{url}\n  -> {r.status}  name={r.filename!r}  "
                  f"size={r.size}  note={r.note!r}")

asyncio.run(main())
