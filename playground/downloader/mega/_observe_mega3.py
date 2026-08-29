
"""mega 观察轮第二批（固定 6 条近期链接，6 次页面加载，0 点击 0 下载）。
目标：撞到活链，看清 file 页 / folder 页的 DOM 结构（文件名/体积/下载按钮）、
cs? API 的活链响应形态。"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

LINKS = [
    "https://mega.nz/file/mh4QhYLZ#ScK1HkZbBymamt6dPfIipHicde4qNTRS17rsCHFMSrw",
    "https://mega.nz/file/7hB2WbaD#KuV2r-Wa9CuaZXYEdW93na8vDTzGIqvuV6IbFBpgxt4",
    "https://mega.nz/folder/J1tViZLa#LSBfQTWLTuGXnuStQmSHvA",
    "https://mega.nz/folder/8CUQWCaJ#TYHkV2PChoScpnUXObC0nA",
    "https://mega.nz/folder/csV3XZrZ#cboB9LJVf--wHQ-WBJsIGA",
    "https://mega.nz/folder/hS0XmIgL#afw2rN0BPH9pURsw7kIeTw",
]


def squeeze(s: str, n: int = 700) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:n]


async def observe(engine, url: str):
    print(f"\n{'=' * 70}\n== {url}")
    page = await engine.context.new_page()
    records = []

    def on_request(r):
        if r.resource_type in ("xhr", "fetch"):
            try:
                pd = squeeze(r.post_data or "", 250)
            except Exception:
                pd = ""
            records.append({"req": r, "url": r.url[:150], "post": pd, "body": None})

    async def grab(rec, resp):
        try:
            rec["body"] = squeeze(await resp.text(), 800)
        except Exception as e:
            rec["body"] = f"<{type(e).__name__}>"

    def on_response(resp):
        if resp.request.resource_type not in ("xhr", "fetch"):
            return
        for rec in records:
            if rec["req"] is resp.request and rec["body"] is None:
                asyncio.ensure_future(grab(rec, resp))
                break

    page.on("request", on_request)
    page.on("response", on_response)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        last_title = None
        for i in range(18):
            t = await page.title()
            if i in (0, 5, 17) or t != last_title:
                print(f"[{(i + 1) * 1.0:4.1f}s] title={t!r}")
            last_title = t
            await page.wait_for_timeout(1000)
        body = await page.locator("body").inner_text()
        print(f"body: {squeeze(body, 900)}")
        dl_btns = page.get_by_role("button", name=re.compile(r"download|下载", re.I))
        n_dl = await dl_btns.count()
        print(f"名字含 download/下载 的按钮 {n_dl} 个")
        for i in range(min(n_dl, 6)):
            print(f"   [{i}] {squeeze(await dl_btns.nth(i).inner_text(), 80)!r}")
        classes = await page.evaluate(
            "() => { const c = {};"
            " for (const el of document.querySelectorAll('div,tr,td,span,a'))"
            "  for (const k of el.classList || [])"
            "   if (/row|item|file|name|size|download/i.test(k)) c[k] = (c[k]||0)+1;"
            " return Object.entries(c).sort((x,y)=>y[1]-x[1]).slice(0,15); }")
        print(f"row/item/file 相关 class 频次: {classes}")
        print(f"XHR/fetch 共 {len(records)} 条，cs? 响应:")
        for rec in records:
            if "api.mega" not in rec["url"]:
                continue
            print(f"   post: {rec['post']}")
            print(f"   resp: {rec['body']}")
    finally:
        await page.close()


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        for u in LINKS:
            await observe(engine, u)
        print("\n完成，3s 后关浏览器")
        await asyncio.sleep(3)


asyncio.run(main())
