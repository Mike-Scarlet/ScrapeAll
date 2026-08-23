
"""gofile 页面观察第 2 轮（同样固定 3 条；3 次页面加载，0 下载）。
SPA 内容不渲染在首屏，这轮抓：页面自己发的 XHR 状态/返回体、10s 后正文、
localStorage token、截图。"""
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

URLS = [
    "https://gofile.io/d/UYEU7v",
    "https://gofile.io/d/iCM2zq",
    "https://gofile.io/d/AuxExhX6",
]
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def squeeze(s: str, n: int = 700) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:n]


async def observe(engine, url: str, shot: str | None):
    page = await engine.context.new_page()
    xhr_log = []
    async def on_response(resp):
        u = resp.url
        if resp.request.resource_type in ("xhr", "fetch") or "gofile" in u:
            try:
                body = squeeze(await resp.text(), 500)
            except Exception:
                body = "<no body>"
            xhr_log.append((resp.status, resp.request.method, u, body))
    page.on("response", lambda r: asyncio.ensure_future(on_response(r)))
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(10000)
        print(f"\n===== {url}  http={resp.status if resp else '?'}  final={page.url}")
        print(f"title={await page.title()!r}")
        body = await page.locator("body").inner_text()
        print(f"body@10s: {squeeze(body)}")
        ls = await page.evaluate(
            """() => { const o = {}; for (let i = 0; i < localStorage.length; i++) {
              const k = localStorage.key(i);
              o[k] = (localStorage.getItem(k) || '').slice(0, 120); } return o; }""")
        print(f"localStorage keys: {list(ls)}")
        for k, v in ls.items():
            print(f"   {k} = {v!r}")
        print(f"XHR/fetch 共 {len(xhr_log)} 条:")
        for status, method, u, body in xhr_log[:15]:
            print(f"   [{status}] {method} {u[:110]}")
            if "api.gofile" in u or "/contents" in u or "/download" in u:
                print(f"        body: {body}")
        if shot:
            await page.screenshot(path=shot, full_page=False)
            print(f"截图: {shot}")
    finally:
        await page.close()


async def main():
  async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
    await observe(engine, URLS[0], os.path.join(_ROOT, "playground", "_gofile_p1.png"))
    for u in URLS[1:]:
      await observe(engine, u, None)
  print("\n完成")


asyncio.run(main())
