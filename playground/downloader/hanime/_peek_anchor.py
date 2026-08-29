# 一次性：开 download 页（stealth，同 profile 同代理），把 table.download-table
# 每行锚点的 outerHTML 抠出来看 href/data-url/download 形态，决定下载触发方式。
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.browser.session import BrowserSession
from config import DOWNLOADER_PROXY_SERVER

VID = sys.argv[1] if len(sys.argv) > 1 else "404842"
URL = f"https://hanime1.me/download?v={VID}"

JS = """() => {
  const out = [];
  for (const tr of document.querySelectorAll('table.download-table tr')) {
    const a = tr.querySelector('a[data-url]');
    if (a) out.push({row: tr.innerText.trim().replace(/\\s+/g, ' '),
                     html: a.outerHTML});
  }
  return out;
}"""


async def main():
  async with BrowserSession(DOWNLOADER_PROXY_SERVER, stealth=True) as session:
    page = await session.new_page()
    resp = await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
    print(f"http={resp.status if resp else '?'} url={page.url}")
    try:
      await page.wait_for_selector("table.download-table a[data-url]", timeout=15000)
    except Exception:
      print("表格没等到")
      return
    await page.wait_for_timeout(1500)
    rows = await page.evaluate(JS)
    print(f"共 {len(rows)} 行锚点：")
    for r in rows:
      print(f"  row: {r['row']}")
      print(f"  anchor: {r['html']}")
    # 页面上还挂了哪些监听（粗看 onclick 属性/相邻广告脚本标记）
    ads = await page.evaluate(
        "() => ({exo: !!document.querySelector('script[src*=\"exoclick\"], iframe[src*=\"exoclick\"]'),"
        " juicy: !!document.querySelector('script[src*=\"juicy\"], iframe[src*=\"juicy\"]')})")
    print(f"广告标记: {ads}")
    await page.close()


asyncio.run(main())
