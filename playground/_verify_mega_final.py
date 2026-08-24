
"""mega 批次 B：两条路径真实落盘（用户已批准，合计约 87MB）。

  1) folder ZIP：真紅 hS0XmIgL -> fm-download -> 下载为ZIP -> save_as
     -> 解压校验（文件数/体积/funscript JSON 合法性）
  2) file 页：7hB2WbaD isami_ride 46.9MB -> 点主 CTA js-download
     （若弹"用桌面 app"劝导框则点『继续使用浏览器』）-> save_as -> 校验字节数
落盘都在 data/eroscripts/files/_verify/。"""
import asyncio
import json
import os
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import TimeoutError as PWTimeoutError

from scrape_all.downloader.engine import DownloadEngine
from scrape_all.downloader.fsutil import sanitize_filename
from config import DOWNLOADER_PROXY_SERVER

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VERIFY = os.path.join(_ROOT, "data", "eroscripts", "files", "_verify")

FOLDER = "https://mega.nz/folder/hS0XmIgL#afw2rN0BPH9pURsw7kIeTw"
FILEPG = "https://mega.nz/file/7hB2WbaD#KuV2r-Wa9CuaZXYEdW93na8vDTzGIqvuV6IbFBpgxt4"
FILE_BYTES = 49_202_734          # 批次二观察时 a:"g" 响应里的 s 字段


def squeeze(s: str, n: int = 300) -> str:
    return " ".join((s or "").split())[:n]


async def main():
    os.makedirs(_VERIFY, exist_ok=True)
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:

        # ---- 1) folder ZIP ----
        print("== 1) folder 真紅 -> ZIP 整夹下载")
        page = await engine.context.new_page()
        hits = []
        page.on("request", lambda r: hits.append(1)
                if "userstorage.mega" in r.url else None)
        try:
            await page.goto(FOLDER, wait_until="domcontentloaded", timeout=45000)
            await page.locator("a.mega-node.fm-item").first.wait_for(
                state="visible", timeout=20000)
            await page.locator("button.fm-download").click()
            await page.locator(".fm-download-menu").wait_for(
                state="visible", timeout=8000)
            t0 = time.monotonic()
            async with page.expect_download(timeout=300000) as dl_info:
                await page.locator(
                    ".fm-download-menu button:has(.icon-download-zip)").click()
            dl = await dl_info.value
            print(f"事件（{time.monotonic() - t0:.0f}s）: "
                  f"suggested={dl.suggested_filename!r}")
            dest = os.path.join(_VERIFY, sanitize_filename(dl.suggested_filename))
            await dl.save_as(dest)
            sz = os.path.getsize(dest)
            print(f"落盘: {dest} ({sz:,} B)，分块请求 {len(hits)} 个")

            with zipfile.ZipFile(dest) as zf:
                bad = zf.testzip()
                names = zf.namelist()
                print(f"zip 完整性: {'OK' if bad is None else f'损坏: {bad}'}，"
                      f"{len(names)} 个条目")
                total = 0
                for i in zf.infolist():
                    total += i.file_size
                    print(f"   {i.file_size:>12,}  {i.filename}")
                print(f"解压总字节: {total:,}")
                main_fs = next((n for n in names if n.endswith(".funscript")
                                and not n.endswith((".pitch.funscript",
                                                   ".roll.funscript",
                                                   ".surge.funscript",
                                                   ".sway.funscript",
                                                   ".twist.funscript"))), None)
                if main_fs:
                    data = json.loads(zf.read(main_fs))
                    n_act = len(data.get("actions") or [])
                    print(f"主 funscript 合法 JSON，actions={n_act}，"
                          f"range={data.get('range')} 版本={data.get('version')}")
        finally:
            await page.close()

        # ---- 2) file 页 ----
        print("\n== 2) file 页 isami_ride -> 主 CTA 下载")
        page = await engine.context.new_page()
        hits = []
        page.on("request", lambda r: hits.append(1)
                if "userstorage.mega" in r.url else None)
        try:
            await page.goto(FILEPG, wait_until="domcontentloaded", timeout=45000)
            name_el = page.locator(".dl-header .fileinfo .filename .name")
            await name_el.wait_for(state="visible", timeout=20000)
            nm = await name_el.inner_text()
            ext = await page.locator(".dl-header .fileinfo .filename .ext").inner_text()
            sz_txt = await page.locator(".dl-header .fileinfo .size").inner_text()
            print(f"probe 读数: name={nm!r} ext={ext!r} size={sz_txt!r}")
            t0 = time.monotonic()
            async with page.expect_download(timeout=300000) as dl_info:
                await page.locator("button.mega-button.positive.js-download").click()
                try:
                    nag = page.locator("button.continue-with-browser")
                    await nag.wait_for(state="visible", timeout=4000)
                    print("出现 app 劝导框 -> 点『继续使用浏览器』")
                    await nag.click()
                except PWTimeoutError:
                    print("无 app 劝导框，直接下载")
            dl = await dl_info.value
            print(f"事件（{time.monotonic() - t0:.0f}s）: "
                  f"suggested={dl.suggested_filename!r}")
            dest = os.path.join(_VERIFY, sanitize_filename(dl.suggested_filename))
            await dl.save_as(dest)
            sz = os.path.getsize(dest)
            ok = "对上" if sz == FILE_BYTES else f"不符（期望 {FILE_BYTES:,}）"
            print(f"落盘: {dest} ({sz:,} B) 与 API 字节数{ok}，"
                  f"分块请求 {len(hits)} 个")
        finally:
            await page.close()
        print("\n完成，3s 后关浏览器")
        await asyncio.sleep(3)


asyncio.run(main())
