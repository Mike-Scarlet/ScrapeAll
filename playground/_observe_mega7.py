
"""mega 批次 A：ZIP 下载机制实验 + file 页按钮 dump。

  1) folder 真紅（39.5MB，最小活夹）：
     - 载入后读初始 ui-selected 集合（pp1.png 疑案留证据）
     - 点 button.fm-download -> 菜单 -> 「下载为ZIP」-> 等下载事件
     - 记录：点击到事件的耗时（判断直链 vs 页面内拉）、suggested 名
     - cancel；userstorage 请求计数佐证机制
  2) file 页 mh4QhYLZ（144.8MB，只读不点）：35 个 download 元素全 dump
     + .dl-header 结构（找大下载按钮和体积文本）
"""
import asyncio
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

FOLDER = "https://mega.nz/folder/hS0XmIgL#afw2rN0BPH9pURsw7kIeTw"
FILEPG = "https://mega.nz/file/mh4QhYLZ#ScK1HkZbBymamt6dPfIipHicde4qNTRS17rsCHFMSrw"


def squeeze(s: str, n: int = 500) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:n]


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        # ---- 1) folder：初始选中 + ZIP 实验 ----
        page = await engine.context.new_page()
        storage_hits = []
        page.on("request", lambda r: storage_hits.append(time.monotonic())
                if "userstorage.mega" in r.url else None)
        try:
            await page.goto(FOLDER, wait_until="domcontentloaded", timeout=45000)
            await page.locator("a.mega-node.fm-item").first.wait_for(
                state="visible", timeout=20000)
            init_sel = await page.evaluate(
                """() => [...document.querySelectorAll('a.mega-node.ui-selected')]
                     .map(a => ({id: a.id,
                                 name: (a.querySelector('.fm-item-name')||{})
                                        .textContent.trim()}))""")
            print(f"初始选中集合（未做任何点击）: {init_sel}")

            await page.locator("button.fm-download").click()
            await page.locator(".fm-download-menu").wait_for(
                state="visible", timeout=8000)
            print("下载菜单已弹出（未选中任何行的状态下）")

            print("点『下载为ZIP』并等下载事件（最长 150s）...")
            t0 = time.monotonic()
            try:
                async with page.expect_download(timeout=150000) as dl_info:
                    await page.locator(
                        ".fm-download-menu button:has(.icon-download-zip)"
                    ).click()
                dl = await dl_info.value
                dt = time.monotonic() - t0
                print(f"下载事件 OK（点击后 {dt:.1f}s 出现）: "
                      f"suggested={dl.suggested_filename!r}")
                await dl.cancel()
                print("已 cancel")
            except Exception as e:
                print(f"下载事件失败: {type(e).__name__}: {squeeze(str(e), 200)}")
            print(f"userstorage 请求 {len(storage_hits)} 个"
                  + (f"，首个出现在点击后 {storage_hits[0] - t0:.1f}s"
                     if storage_hits else ""))
        finally:
            await page.close()

        # ---- 2) file 页：全量 dump ----
        page = await engine.context.new_page()
        try:
            await page.goto(FILEPG, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(10000)
            n = await page.locator("[class*='download']").count()
            print(f"\nfile 页 class 含 download 的元素 {n} 个:")
            for i in range(n):
                html = await page.locator("[class*='download']").nth(i).evaluate(
                    "e => e.tagName + ' | ' + String(e.className).slice(0,70) "
                    "+ ' | ' + e.outerHTML.slice(0, 130)")
                print(f"   [{i}] {squeeze(html, 180)}")
            hdr = await page.locator(".dl-header").first.evaluate(
                "e => e.outerHTML.slice(0, 1500)")
            print(f"\n.dl-header 结构:\n{squeeze(hdr, 1500)}")
        finally:
            await page.close()
        print("\n完成，3s 后关浏览器")
        await asyncio.sleep(3)


asyncio.run(main())
