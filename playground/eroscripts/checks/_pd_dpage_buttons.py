# 摸 /d 页下载按钮的稳定选择器：两个 /d 样本（一视频一未知类型），
# 列出所有含 download 字样按钮的 outerHTML 前 300 字符
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from config import DOWNLOADER_PROXY_SERVER
from scrape_all.downloader.engine import DownloadEngine

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PIDS = ["E1Kk51Ls", "yZFyovdG"]


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        for pid in PIDS:
            async with engine.slot():
                page = await engine.context.new_page()
                try:
                    resp = await page.goto(f"https://pixeldrain.com/d/{pid}",
                                           wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(1500)
                    title = await page.title()
                    btns = page.locator("button")
                    n = await btns.count()
                    print(f"\n== {pid}  http={resp.status if resp else '?'}  title={title!r}  buttons={n}")
                    for i in range(n):
                        html = await btns.nth(i).evaluate("el => el.outerHTML")
                        text = (await btns.nth(i).inner_text()).strip().replace("\n", "/")
                        if "download" in text.lower() or "download" in html.lower():
                            print(f"  [{i}] text={text!r}")
                            print(f"      html={html[:300]}")
                finally:
                    await page.close()

asyncio.run(main())
