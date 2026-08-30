# 设计前置调查（只读）：
#  1) 正常已下载的 pixeldrain 样本（/u /d /l 三种形态各取一），同 id 互换形态看
#     content-type / content-disposition —— /d 对正常文件是页面还是 attachment
#  2) E1Kk51Ls 的 /d 页面上有没有 toolbar_button（Download 按钮），download 流能否复用
import os
import re
import sys
import asyncio
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from config import DOWNLOADER_PROXY_SERVER
from scrape_all.downloader.engine import DownloadEngine
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                  "data", "eroscripts.db")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def swap_form(url, to):
    p = urlsplit(url)
    path = re.sub(r"^/(u|d|l|api/file|api/list)/", f"/{to}/", p.path)
    return f"{p.scheme}://{p.netloc}{path}"


with TopicStore(DB) as store:
    rows = store.db.QueryRecords(EroLink, where="host = ?", params=["pixeldrain.com"])
dl = [r for r in rows if r.dl_status == "downloaded"]
samples = []
for form in ("u", "d", "l"):
    got = [r.url for r in dl if f"/{form}/" in r.url][:1]
    samples += got
print("正常样本（均已落盘）:")
for u in samples:
    print(f"  {u}")


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        print("\n同 id 互换形态（Range 探头，零正文）:")
        for u in samples:
            for form in ("u", "d"):
                alt = swap_form(u, form)
                r = await engine.probe_headers(alt, park_url="https://pixeldrain.com/")
                h = r.get("headers") or {}
                print(f"  {alt}  -> {r['status']}  ct={h.get('content-type', '?')}"
                      f"  cd={h.get('content-disposition', '-')}")

        print("\nE1Kk51Ls /d 页面按钮面:")
        async with engine.slot():
            page = await engine.context.new_page()
            try:
                await page.goto("https://pixeldrain.com/d/E1Kk51Ls",
                                wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1500)
                btns = page.locator("button.toolbar_button")
                n = await btns.count()
                texts = [await btns.nth(i).inner_text() for i in range(min(n, 6))]
                print(f"  toolbar_button 数量={n}  文本={texts}")
            finally:
                await page.close()

asyncio.run(main())
