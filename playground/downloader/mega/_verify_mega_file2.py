
"""mega file 页下载重试：先扫候选按钮可见性再点（上次 js-download 不可见超时）。
仍走 7hB2WbaD（46.9MB 已批准额度内），点可见候选 -> 处理 app 劝导框 -> 落盘校验。"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from playwright.async_api import TimeoutError as PWTimeoutError

from scrape_all.downloader.engine import DownloadEngine
from scrape_all.downloader.fsutil import sanitize_filename
from config import DOWNLOADER_PROXY_SERVER

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_VERIFY = os.path.join(_ROOT, "data", "eroscripts", "files", "_verify")

FILEPG = "https://mega.nz/file/7hB2WbaD#KuV2r-Wa9CuaZXYEdW93na8vDTzGIqvuV6IbFBpgxt4"
FILE_BYTES = 49_202_734

CANDIDATES = [
    "button.v-btn.simpletip.download",                              # [20] v-btn
    "button.mega-button.action.download-btn",                       # [18] header 动作
    ".dl-header button[data-simpletip='下载']",                     # header 图标
    "button.mega-button.positive.js-download",                      # [21] 上次超时
]


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        page = await engine.context.new_page()
        try:
            await page.goto(FILEPG, wait_until="domcontentloaded", timeout=45000)
            await page.locator(".dl-header .fileinfo .filename .name").wait_for(
                state="visible", timeout=20000)
            await page.wait_for_timeout(3000)
            for sel in CANDIDATES:
                loc = page.locator(sel)
                n = await loc.count()
                vis = []
                for i in range(n):
                    el = loc.nth(i)
                    box = await el.bounding_box()
                    vis.append(bool(box and box["width"] > 0 and box["height"] > 0))
                print(f"{sel!r}: {n} 个，可见 {sum(vis)}")
                if n and any(vis):
                    idx = vis.index(True)
                    t0 = time.monotonic()
                    try:
                        async with page.expect_download(timeout=300000) as dl_info:
                            await loc.nth(idx).click()
                            try:
                                nag = page.locator("button.continue-with-browser")
                                await nag.wait_for(state="visible", timeout=5000)
                                print("  app 劝导框 -> 点『继续使用浏览器』")
                                await nag.click()
                            except PWTimeoutError:
                                pass
                        dl = await dl_info.value
                        print(f"  事件（{time.monotonic() - t0:.0f}s）: "
                              f"suggested={dl.suggested_filename!r}")
                        dest = os.path.join(
                            _VERIFY, sanitize_filename(dl.suggested_filename))
                        await dl.save_as(dest)
                        sz = os.path.getsize(dest)
                        ok = "对上" if sz == FILE_BYTES else \
                            f"不符（期望 {FILE_BYTES:,}）"
                        print(f"  落盘: {dest} ({sz:,} B) 与 API 字节数{ok}")
                        return
                    except PWTimeoutError as e:
                        print(f"  点了但无事件: {e}")
            print("!! 没有可点的可见下载按钮")
        finally:
            await page.close()
        print("完成，3s 后关浏览器")
        await asyncio.sleep(3)


asyncio.run(main())
