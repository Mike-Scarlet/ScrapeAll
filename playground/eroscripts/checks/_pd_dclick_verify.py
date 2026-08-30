# 实现前最后验证（不落盘）：
#  1) /d 页点动作栏 Download 按钮 -> 下载事件一冒头立刻 cancel（验证按钮 + 看真名）
#  2) 体积锚定（计划写进 adapter 的原样逻辑）在 /d 与 /u 页各跑一遍
import os
import re
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from config import DOWNLOADER_PROXY_SERVER
from scrape_all.downloader.engine import DownloadEngine
from scrape_all.downloader.adapters.pixeldrain import parse_size_text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_SIZE_LABEL_RE = re.compile(r"size\s*([\d.]+\s*(?:B|KB|MB|GB|TB))", re.I)


async def labeled_size(page):
    blocks = await page.locator(".stat").evaluate_all(
        "els => els.map(e => e.parentElement.innerText)")
    for text in blocks:
        m = _SIZE_LABEL_RE.search(text or "")
        if m:
            return parse_size_text(m.group(1)), m.group(1)
    return None, None


async def try_button(page, which, label):
    btn = page.locator("button").filter(
        has_text=re.compile(r"download", re.I))
    target = btn.first if which == "first" else btn.last
    try:
        async with page.expect_download(timeout=20000) as dl_info:
            await target.click()
        dl = await dl_info.value
        name = dl.suggested_filename
        await dl.cancel()
        print(f"  [{label}] 下载事件 OK  suggested={name!r}  已 cancel 不落盘")
        return True
    except Exception as e:
        print(f"  [{label}] 无下载事件: {str(e)[:80]}")
        return False


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        for form, pid in (("d", "E1Kk51Ls"), ("u", "PV82t9fy")):
            async with engine.slot():
                page = await engine.context.new_page()
                try:
                    await page.goto(f"https://pixeldrain.com/{form}/{pid}",
                                    wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(1500)
                    print(f"\n== /{form}/{pid}  title={await page.title()!r}")
                    size, raw = await labeled_size(page)
                    print(f"  labeled size = {raw!r} -> {size}")
                    if form == "d":
                        if not await try_button(page, "first", "first(save/Download)"):
                            await try_button(page, "last", "last(download/Download)")
                finally:
                    await page.close()

asyncio.run(main())
