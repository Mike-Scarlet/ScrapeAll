# 设计前置调查第二轮（只读，Range 探头零正文）：
#  1) E1Kk51Ls 的下载入口候选：/d?download 与 /api/file 的响应头（找 attachment）
#  2) /d 页面上全部按钮文本（找下载入口元素）
#  3) 库内 pixeldrain 按 URL 形态 × dl_status 交叉 —— /d 形态是不是重灾区
import os
import re
import sys
import asyncio
from urllib.parse import urlsplit
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from config import DOWNLOADER_PROXY_SERVER
from scrape_all.downloader.engine import DownloadEngine
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
DB = os.path.join(DB, "data", "eroscripts.db")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def form_of(url):
    m = re.match(r"^/(u|d|l|api/file|api/list)/", urlsplit(url).path)
    return m.group(1) if m else "?"


with TopicStore(DB) as store:
    rows = store.db.QueryRecords(EroLink, where="host = ?", params=["pixeldrain.com"])
cross = Counter((form_of(r.url), r.dl_status) for r in rows)
forms = sorted({f for f, _ in cross})
stats = sorted({s for _, s in cross})
print(f"库内 pixeldrain {len(rows)} 条，形态 × dl_status：")
print(f"{'形态':<10}" + "".join(f"{s:<12}" for s in stats))
for f in forms:
    print(f"{f:<10}" + "".join(f"{cross.get((f, s), 0):<12}" for s in stats))


async def main():
    pid = "E1Kk51Ls"
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        print("\n下载入口候选（Range 探头）：")
        for url in (f"https://pixeldrain.com/d/{pid}?download",
                    f"https://pixeldrain.com/api/file/{pid}"):
            r = await engine.probe_headers(url, park_url="https://pixeldrain.com/")
            h = r.get("headers") or {}
            print(f"  {url}  -> {r['status']}  ct={h.get('content-type', '?')}"
                  f"  cd={h.get('content-disposition', '-')}"
                  f"  cr={h.get('content-range', '-')}")

        print("\n/d 页面全部按钮：")
        async with engine.slot():
            page = await engine.context.new_page()
            try:
                await page.goto(f"https://pixeldrain.com/d/{pid}",
                                wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1500)
                texts = [t.strip().replace("\n", "/") for t in
                         await page.locator("button").all_inner_texts()]
                print(f"  button 共 {len(texts)} 个: {texts}")
            finally:
                await page.close()

asyncio.run(main())
