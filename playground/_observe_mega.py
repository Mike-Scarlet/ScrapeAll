
"""mega 观察轮（固定 3 条：1 file + 2 folder；3 次页面加载，0 点击 0 下载）。

每条只做：
  - goto domcontentloaded，记录 document 重定向链（mega.nz 可能跳 mega.io 或补 #!）
  - 轮询 ~20s：title / url 变化（重 SPA，等渲染）
  - 抓 XHR/fetch：URL + 请求体 + 响应体（挤压缩短）——看站内 API 形态（死活/文件名/体积从哪来）
  - body 文本 + 按钮/链接概览（下载按钮、folder 文件行结构）
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

LINKS = [
    "https://mega.nz/file/Lj43zSwJ#YPDytvHKOPLU_bRHt-TgPg0Saml4pwVGsdSXXfRMegY",
    "https://mega.nz/folder/z0JzVIAY#mE2-P2BCbe5i1KjyZ8YfiQ",
    "https://mega.nz/folder/fQEkyQqD#lBWTORFB9Nrl1SRLXvyllA",
]


def squeeze(s: str, n: int = 700) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:n]


async def observe(engine, url: str):
    print(f"\n{'=' * 70}\n== {url}")
    page = await engine.context.new_page()
    docs, apis = [], []

    def on_request(r):
        if r.resource_type == "document":
            docs.append(r.url[:150])
        elif r.resource_type in ("xhr", "fetch"):
            try:
                pd = squeeze(r.post_data or "", 200)
            except Exception:
                pd = ""
            apis.append({"url": r.url[:150], "post": pd, "body": None})

    def on_response(resp):
        if resp.request.resource_type not in ("xhr", "fetch"):
            return
        for rec in apis:
            if rec["url"].startswith(resp.url[:150][:140]) and rec["body"] is None:
                try:
                    rec["body"] = squeeze(resp.text(), 700)
                except Exception as e:
                    rec["body"] = f"<{type(e).__name__}>"
                break

    page.on("request", on_request)
    page.on("response", on_response)
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        print(f"goto: status={resp.status if resp else '?'}")
        print("document 重定向链:")
        for u in docs:
            print(f"   {u}")
        last_title = None
        for i in range(20):
            t = await page.title()
            if i in (0, 4, 19) or t != last_title:
                print(f"[{(i + 1) * 1.0:4.1f}s] title={t!r}  url={page.url[:90]}")
            last_title = t
            await page.wait_for_timeout(1000)
        body = await page.locator("body").inner_text()
        print(f"body: {squeeze(body, 900)}")
        n_btn = await page.locator("button").count()
        n_a = await page.locator("a").count()
        print(f"按钮 {n_btn} 个 / 链接 {n_a} 个")
        dl_btns = page.get_by_role("button", name=re.compile(r"download", re.I))
        n_dl = await dl_btns.count()
        print(f"名字含 download 的按钮 {n_dl} 个")
        if n_dl:
            for i in range(min(n_dl, 5)):
                print(f"   [{i}] {squeeze(await dl_btns.nth(i).inner_text(), 120)!r}")
        print(f"XHR/fetch 共 {len(apis)} 条，含 api 的:")
        for rec in apis:
            if "api" in rec["url"] or "cs?id" in rec["url"]:
                print(f"   -> {rec['url']}")
                if rec["post"]:
                    print(f"      post: {rec['post']}")
                if rec["body"]:
                    print(f"      resp: {rec['body']}")
    finally:
        await page.close()


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        for u in LINKS:
            await observe(engine, u)
        print("\n完成，5s 后关浏览器")
        await asyncio.sleep(5)


asyncio.run(main())
