
"""mega 观察轮 v2：同样固定 3 条（已批准范围），修 v1 的响应体捕获 bug。
v1 结论：三条全死（三种文案），title 不可靠。本轮目标：拿 g.api.mega.co.nz/cs?
的响应体，看 API 层死链错误码长什么样。仍然 0 点击 0 下载。"""
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
    records = []  # [{req, url, post, body}]

    def on_request(r):
        if r.resource_type in ("xhr", "fetch"):
            try:
                pd = squeeze(r.post_data or "", 200)
            except Exception:
                pd = ""
            records.append({"req": r, "url": r.url[:150], "post": pd, "body": None})

    async def grab(rec, resp):
        try:
            rec["body"] = squeeze(await resp.text(), 800)
        except Exception as e:
            rec["body"] = f"<{type(e).__name__}: {e}>"

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
        await page.wait_for_timeout(12000)  # 死链判定 12s 内完成，无需 20s
        body = await page.locator("body").inner_text()
        print(f"body: {squeeze(body, 400)}")
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
