
"""mega 观察轮三 v3：用人工确认的真选择器做点击实验。

  1) folder 真紅：a.mega-node.fm-item 行（title 属性带 "15 KB 文件名"）
     -> 选中最小 funscript -> button.fm-download -> 菜单里"普通下载"
     -> 等下载事件 -> cancel。流量预算 = 该 funscript 本身（KB 级）
  2) file 页 mh4QhYLZ（144.8MB）：只扒 [class*=download] 元素结构，不点
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

FOLDER = "https://mega.nz/folder/hS0XmIgL#afw2rN0BPH9pURsw7kIeTw"
FILEPG = "https://mega.nz/file/mh4QhYLZ#ScK1HkZbBymamt6dPfIipHicde4qNTRS17rsCHFMSrw"

_SIZE_MULT = {"B": 1, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3}


def parse_size(t):
    m = re.search(r"([\d.]+)\s*(B|KB|MB|GB)", t or "")
    if not m:
        return None
    return int(float(m.group(1)) * _SIZE_MULT[m.group(2)])


def squeeze(s: str, n: int = 500) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:n]


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        page = await engine.context.new_page()
        storage_hits = []
        page.on("request", lambda r: storage_hits.append(r.url[:110])
                if "userstorage.mega" in r.url else None)
        try:
            await page.goto(FOLDER, wait_until="domcontentloaded", timeout=45000)
            await page.locator("a.mega-node.fm-item").first.wait_for(
                state="visible", timeout=20000)
            rows = await page.locator("a.mega-node.fm-item").evaluate_all(
                """els => els.map(a => ({
                     id: a.id,
                     name: (a.querySelector('.fm-item-name')||{}).textContent || '',
                     title: a.getAttribute('title') || ''}))""")
            print(f"行数 {len(rows)}")
            for r in rows:
                print(f"   id={r['id']} title={squeeze(r['title'], 60)!r}")
            targets = [r for r in rows if r["name"].strip().endswith(".funscript")]
            targets.sort(key=lambda r: parse_size(r["title"]) or 10 ** 9)
            if not targets:
                print("!! 没找到 funscript 行")
                return
            tgt = targets[0]
            print(f"\n目标（最小 funscript）: id={tgt['id']} {tgt['title']!r}")

            row = page.locator(f"a.mega-node.fm-item#{tgt['id']}")
            await page.locator(
                f"a.mega-node.fm-item#{tgt['id']} .fm-item-name").click()
            await page.wait_for_timeout(800)
            cls = await row.get_attribute("class")
            print(f"点击后行 class: {cls!r}")
            if "ui-selected" not in (cls or ""):
                print("!! 行未进入选中态，谨慎起见不点下载，退出")
                return

            await page.locator("button.fm-download").click()
            menu = page.locator(".fm-download-menu")
            await menu.wait_for(state="visible", timeout=8000)
            print("下载菜单已弹出")

            print("点『普通下载』并等下载事件（最长 150s）...")
            try:
                async with page.expect_download(timeout=150000) as dl_info:
                    await page.locator(
                        ".fm-download-menu button:has(.icon-download-standard)"
                    ).click()
                dl = await dl_info.value
                print(f"下载事件 OK: suggested={dl.suggested_filename!r}")
                await dl.cancel()
                print("已 cancel")
            except Exception as e:
                print(f"下载事件失败: {type(e).__name__}: {squeeze(str(e), 200)}")
            print(f"userstorage 请求 {len(storage_hits)} 个")
            for u in storage_hits[:6]:
                print(f"   {u}")
        finally:
            await page.close()

        # ---- 2) file 页：只扒下载按钮结构 ----
        page = await engine.context.new_page()
        try:
            await page.goto(FILEPG, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(10000)
            btns = page.locator("[class*='download']")
            n = await btns.count()
            print(f"\nfile 页 class 含 download 的元素 {n} 个:")
            for i in range(min(n, 6)):
                html = await btns.nth(i).evaluate("e => e.outerHTML.slice(0, 200)")
                print(f"   [{i}] {squeeze(html, 200)}")
        finally:
            await page.close()
        print("\n完成，3s 后关浏览器")
        await asyncio.sleep(3)


asyncio.run(main())
