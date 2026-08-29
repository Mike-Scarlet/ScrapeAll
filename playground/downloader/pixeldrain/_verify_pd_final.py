
"""pixeldrain 页面流 adapter 最终验证（固定清单，无遍历）。

  1) 探活 4 条已知链接（活/死文件、活/死列表）—— 4 次页面加载
  2) 幂等：已下载的 14MB 文件应 skipped，不点按钮 —— 1 次页面加载
  3) 真实点击下载 1 条指定链接 —— 1 次页面加载 + 1 次下载（流量 = 文件本身）
  4) 列表按钮：点击 -> 下载事件 -> 立刻 cancel —— 1 次页面加载，几乎 0 流量

共 7 次页面加载 + 1 次真实下载。不做任何库内遍历。
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.downloader.adapters import adapter_for
from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_VERIFY = os.path.join(_ROOT, "data", "eroscripts", "files", "_verify")

# 已知状态链接（此前多轮验证确认过，无需再探）
ALIVE_FILE = "https://pixeldrain.com/u/QG5Pqjpq"     # 14MB，已下载过
DEAD_FILE = "https://pixeldrain.com/u/kV6Aqw71"
ALIVE_LIST = "https://pixeldrain.com/l/dQotgt6u"     # 2 文件 ~272MB
DEAD_LIST = "https://pixeldrain.com/l/x2CLfTjy"
# 真实下载目标：此前 Range 探过，51MB（库内最小的未下载活链）
REAL_DL = "https://pixeldrain.com/u/QJSXZzdn"


async def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--download-url", default=REAL_DL,
                  help="真实点击下载的链接（默认 51MB 的 QJSXZzdn；传空跳过）")
  args = ap.parse_args()

  adapter = adapter_for("https://pixeldrain.com/u/x")
  async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:

    print("== 1) 探活 4 条已知链接")
    for u in (ALIVE_FILE, DEAD_FILE, ALIVE_LIST, DEAD_LIST):
      p = await adapter.probe(engine, u)
      print(f"   {u} -> {p.status} name={p.filename!r} size={p.size} {p.note}")

    print("== 2) 幂等（已下载过 -> skipped，不点按钮）")
    r = await adapter.download(engine, ALIVE_FILE, _VERIFY)
    print(f"   -> {r.status} {r.note}")

    if args.download_url:
      print(f"== 3) 真实点击下载 {args.download_url}")
      r = await adapter.download(engine, args.download_url, _VERIFY)
      print(f"   -> {r.status} size={r.size} path={r.path} {r.note}")
    else:
      print("== 3) 跳过真实下载")

    print("== 4) 列表按钮链路（点击->事件->cancel，不拉数据）")
    page = await engine.context.new_page()
    try:
      await page.goto(ALIVE_LIST, wait_until="domcontentloaded", timeout=30000)
      await page.wait_for_timeout(1500)
      btn = page.locator('button[title*="zip archive"]').first
      await btn.wait_for(state="visible", timeout=15000)
      async with page.expect_download(timeout=30000) as dl_info:
        await btn.click()
      download = await dl_info.value
      print(f"   下载事件 OK: suggested={download.suggested_filename!r}，cancel")
      await download.cancel()
    except Exception as e:
      print(f"   失败: {e}")
    finally:
      await page.close()

    print("\n完成，5s 后关浏览器")
    await asyncio.sleep(5)


asyncio.run(main())
