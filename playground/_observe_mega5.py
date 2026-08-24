
"""mega 观察轮三 v2：行选择器 evaluate 查不到（疑似 shadow DOM），改用
Playwright 定位器（穿透 open shadow root）从 funscript 文本往上爬祖先。
仍然只点最小 funscript，file 页不点。"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

FOLDER = "https://mega.nz/folder/hS0XmIgL#afw2rN0BPH9pURsw7kIeTw"
FILEPG = "https://mega.nz/file/mh4QhYLZ#ScK1HkZbBymamt6dPfIipHicde4qNTRS17rsCHFMSrw"


def squeeze(s: str, n: int = 500) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:n]


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        page = await engine.context.new_page()
        storage_hits = []
        page.on("request", lambda r: storage_hits.append(r.url[:100])
                if "userstorage.mega" in r.url else None)
        try:
            await page.goto(FOLDER, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(18000)  # 与第二批同节奏

            for sel in ('[class*="data-item"]', '.fm-row', '[class*="file-name"]'):
                print(f"locator({sel!r}) -> {await page.locator(sel).count()}")

            names = page.get_by_text(re.compile(r"\.funscript$"))
            n = await names.count()
            print(f"以 .funscript 结尾的文本节点 {n} 个")
            if not n:
                print("!! 仍找不到，放弃")
                return

            # 爬第一个 funscript 文本节点的祖先链，找行容器
            chain = await names.first.evaluate(
                """el => { const out = [];
                  let cur = el;
                  for (let i = 0; i < 8 && cur; i++) {
                    out.push({tag: cur.tagName,
                              cls: String(cur.className).slice(0, 70),
                              txt: (cur.textContent || '').trim().slice(0, 50)});
                    cur = cur.parentElement || (cur.getRootNode && cur.getRootNode().host);
                  }
                  return out; }""")
            print("祖先链:")
            for c in chain:
                print(f"   <{c['tag']} class={c['cls']!r}> txt={c['txt']!r}")

            # 尝试右键“行容器”（链上 tag=tr/div 且 class 含 row/item 的最浅一个）
            row_idx = next((i for i, c in enumerate(chain)
                            if i > 0 and re.search(r"row|item", c["cls"] or "", re.I)), 1)
            row_loc = names.first if row_idx == 1 else \
                page.get_by_text(chain[row_idx]["txt"].split(".funscript")[0] + ".funscript",
                                 exact=False).first
            await row_loc.click(button="right")
            await page.wait_for_timeout(1500)
            items = await page.locator(
                '[role="menuitem"], .context-menu-item, .dropdown-item'
            ).all_inner_texts()
            items = [squeeze(t, 40) for t in items if t.strip()][:15]
            print(f"右键菜单项: {items}")

            dl_item = page.get_by_role("menuitem", name=re.compile(r"下载|download", re.I))
            n_dl = await dl_item.count()
            print(f"菜单含 下载/download 的项 {n_dl} 个")

            print("\n等下载事件（最长 150s）...")
            try:
                async with page.expect_download(timeout=150000) as dl_info:
                    if n_dl:
                        await dl_item.first.click()
                    else:
                        await row_loc.click()
                        await page.wait_for_timeout(800)
                        await page.get_by_role("button", name="下载").first.click()
                dl = await dl_info.value
                print(f"下载事件 OK: suggested={dl.suggested_filename!r}")
                await dl.cancel()
                print("已 cancel")
            except Exception as e:
                print(f"下载事件失败: {type(e).__name__}: {squeeze(str(e), 200)}")
            finally:
                print(f"userstorage 请求 {len(storage_hits)} 个")
                for u in storage_hits[:5]:
                    print(f"   {u}")
        finally:
            await page.close()

        # ---- file 页：扒下载按钮 ----
        page = await engine.context.new_page()
        try:
            await page.goto(FILEPG, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(10000)
            for sel in ('[class*="download"]', 'button', 'a[class*="big"]'):
                cnt = await page.locator(sel).count()
                print(f"file 页 locator({sel!r}) -> {cnt}")
            btns = await page.locator(
                '[class*="download"]').all()
            print(f"file 页 class 含 download 的元素 {len(btns)} 个:")
            for b in btns[:6]:
                html = await b.evaluate("e => e.outerHTML.slice(0, 200)")
                print(f"   {squeeze(html, 200)}")
        finally:
            await page.close()
        print("\n完成，3s 后关浏览器")
        await asyncio.sleep(3)


asyncio.run(main())
