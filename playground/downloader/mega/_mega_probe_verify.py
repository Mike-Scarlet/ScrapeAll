# mega 双视图修复验证（零下载）：真跑 MegaAdapter.probe 确认两个网格视图夹
# 不再误报 unknown；顺带零点击统计下载按钮相关选择器，确认 _download_folder_zip
# 的按钮流（button.fm-download / .fm-download-menu / ZIP 菜单项）在这种视图存在。
#   python playground/downloader/mega/_mega_probe_verify.py
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from python_general_lib.environment_setup.logging_setup import *
import logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

from config import DOWNLOADER_PROXY_SERVER
from scrape_all.browser.session import BrowserSession
from scrape_all.downloader.adapters.mega import MegaAdapter

URLS = [
  ("314864", "https://mega.nz/folder/NwcnGTbT#S1SNTBE9Xs8BJ36UM8KfAA"),
  ("320322", "https://mega.nz/folder/9DhEzYDS#EmoLKuto-e1i3XmoLN-7Tw"),
]
BTN_SELS = ["button.fm-download", ".fm-download-menu", ".icon-download-zip"]


async def main():
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  adapter = MegaAdapter()
  class _Slot:                     # probe 要过 engine.slot()；单页直通
    async def __aenter__(self):
      return self
    async def __aexit__(self, *a):
      return False
  class _Engine:
    def __init__(self, ctx):
      self.context = ctx
    def slot(self):
      return _Slot()
  async with BrowserSession(DOWNLOADER_PROXY_SERVER) as session:
    engine = _Engine(session.context)
    for tag, url in URLS:
      print(f"\n===== {tag} {url}")
      probe = await adapter.probe(engine, url)
      print(f"probe={probe.status} size={probe.size} files={len(probe.files or [])}")
      print(f"  filename={probe.filename!r}")
      print(f"  note={probe.note}")
      page = await session.new_page()
      await page.goto(url, wait_until="domcontentloaded", timeout=30000)
      try:
        await page.locator("table.grid-table tbody tr.megaListItem").first \
            .wait_for(state="visible", timeout=40000)
        counts = await page.evaluate(
            """(sels) => Object.fromEntries(
                 sels.map(s => [s, document.querySelectorAll(s).length]))""",
            BTN_SELS)
        print(f"  下载按钮选择器命中（零点击）: {counts}")
      except Exception as e:
        print(f"  行渲染等待失败: {e}")
      finally:
        await page.close()


asyncio.run(main())
