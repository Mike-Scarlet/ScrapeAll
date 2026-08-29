# 一次性实验：download 页里合成 <a href=data-url download=真名>，Playwright
# 真实点击（CDP=用户手势，跨域 download 属性才生效）→ expect_download → 落盘
# data/eroscripts/files/_verify/。验证 hanime 下载腿的可行触发方式。
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.browser.session import BrowserSession
from config import DOWNLOADER_PROXY_SERVER

VID = sys.argv[1] if len(sys.argv) > 1 else "404842"
URL = f"https://hanime1.me/download?v={VID}"
DEST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data", "eroscripts", "files", "_verify")

ROWS_JS = """() => Array.from(document.querySelectorAll(
    'table.download-table tr')).map((tr, i) => {
  const a = tr.querySelector('a[data-url]');
  if (!a) return null;
  return {i, url: a.dataset.url || '',
          name: a.getAttribute('download') || '',
          quality: tr.querySelectorAll('td')[1]?.innerText.trim() || ''};
}).filter(Boolean)"""


def best_row(rows):
  import re
  def res(q):
    m = re.search(r"(\\d{3,4})\\s*p", q, re.I)
    return int(m.group(1)) if m else -1
  return max(enumerate(rows), key=lambda kv: (res(kv[1]["quality"]), -kv[0]))[1]


async def main():
  os.makedirs(DEST_DIR, exist_ok=True)
  async with BrowserSession(DOWNLOADER_PROXY_SERVER, stealth=True) as session:
    page = await session.new_page()
    resp = await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
    print(f"http={resp.status if resp else '?'} url={page.url}")
    await page.wait_for_selector("table.download-table a[data-url]", timeout=15000)
    await page.wait_for_timeout(1200)
    rows = await page.evaluate(ROWS_JS)
    print(f"{len(rows)} 行: {[r['quality'] for r in rows]}")
    best = best_row(rows)
    print(f"选档: {best['quality']} name={best['name']!r}")
    print(f"data-url: {best['url']}")

    # 合成干净锚点（不带 exoclick/juicyads 类，不经过站内 JS 接管）
    await page.evaluate("""([url, name]) => {
      const a = document.createElement('a');
      a.id = '__dl_synth';
      a.href = url; a.download = name;
      // 要可点击（Playwright 拒点不可见元素）：角落 8x8、近乎全透明
      a.style.cssText = 'position:fixed;left:4px;top:4px;width:8px;height:8px;'
                        + 'opacity:0.01;z-index:2147483647;display:block;';
      document.body.appendChild(a);
      return true;
    }""", [best["url"], best["name"]])

    pages_before = list(session.context.pages)
    try:
      async with page.expect_download(timeout=60000) as dl_info:
        await page.locator("#__dl_synth").click()
      dl = await dl_info.value
      print(f"下载事件! suggested={dl.suggested_filename!r}")
      dest = os.path.join(DEST_DIR, dl.suggested_filename or f"hanime_{VID}.mp4")
      await dl.save_as(dest)
      print(f"落盘: {dest} ({os.path.getsize(dest)} bytes)")
    except Exception as e:
      print(f"失败: {type(e).__name__}: {e}")
    new_pages = [p for p in session.context.pages if p not in pages_before]
    if new_pages:
      for p in new_pages:
        print(f"冒出新页面(关掉): {p.url}")
        await p.close()
    await page.close()


asyncio.run(main())
