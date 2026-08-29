# 一次性（只读诊断）：v=407591 两次稳定 "TypeError: Failed to fetch" 取证。
# 复刻 adapter 流程但把 goto(data_url) 的异常暴露出来（adapter 里 pass 掉了），
# 并用 no-cors 对照区分网络层失败 vs CORS 拒绝。不落盘（body 立即 cancel）。
import asyncio
import os
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.browser.session import BrowserSession
from config import DOWNLOADER_PROXY_SERVER

VID = sys.argv[1] if len(sys.argv) > 1 else "407591"
URL = f"https://hanime1.me/download?v={VID}"

ROWS_JS = """() => Array.from(document.querySelectorAll(
    'table.download-table tr')).map((tr, i) => {
  const a = tr.querySelector('a[data-url]');
  if (!a) return null;
  const tds = tr.querySelectorAll('td');
  return {i, url: a.dataset.url || '',
          name: a.getAttribute('download') || '',
          quality: tds.length > 1 ? tds[1].innerText.trim() : ''};
}).filter(Boolean)"""

FETCH_PROBE_JS = """async (url) => {
  const out = {};
  try {
    const r = await fetch(url, {credentials: "include"});
    out.normal = "HTTP " + r.status + " len=" + (r.headers.get("content-length") || "?")
                 + " type=" + (r.headers.get("content-type") || "?");
    r.body.cancel();
  } catch (e) { out.normal = "THROW " + String(e); }
  try {
    const r2 = await fetch(url, {mode: "no-cors", credentials: "include"});
    out.no_cors = "opaque ok type=" + r2.type;
  } catch (e) { out.no_cors = "THROW " + String(e); }
  return out;
}"""


async def main():
  async with BrowserSession(DOWNLOADER_PROXY_SERVER, stealth=True) as session:
    page = await session.new_page()
    resp = await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
    print(f"[1] download 页 http={resp.status if resp else '?'} url={page.url}")
    await page.wait_for_selector("table.download-table a[data-url]", timeout=15000)
    await page.wait_for_timeout(1200)
    rows = await page.evaluate(ROWS_JS)
    print(f"[2] 表格 {len(rows)} 行:")
    for r in rows:
      host = urlsplit(r["url"]).netloc
      print(f"    {r['quality']:<14} {host}  name={r['name']!r}")
    best = max(enumerate(rows), key=lambda kv: (
        int(__import__("re").search(r"(\d{3,4})p", kv[1]["quality"]).group(1))
        if __import__("re").search(r"(\d{3,4})p", kv[1]["quality"]) else -1,
        -kv[0]))[1]
    data_url = best["url"]
    print(f"[3] 选档: {best['quality']} {data_url}")

    print(f"[4] goto 前页面 origin: {urlsplit(page.url).scheme}://{urlsplit(page.url).netloc}")
    size = None
    try:
      r2 = await page.goto(data_url, timeout=30000)
      clen = r2.headers.get("content-length") if r2 else None
      if clen and clen.isdigit():
        size = int(clen)
      print(f"[5] goto OK http={r2.status if r2 else '?'} 最终url={page.url} "
            f"len={clen} size={size}")
    except Exception as e:
      print(f"[5] goto 抛异常: {type(e).__name__}: {e}")
    print(f"[6] goto 后页面 origin: {urlsplit(page.url).scheme}://{urlsplit(page.url).netloc} "
          f"(CDN host: {urlsplit(data_url).netloc})")

    out = await page.evaluate(FETCH_PROBE_JS, data_url)
    print(f"[7] fetch 探测: normal={out['normal']}")
    print(f"           no_cors={out['no_cors']}")
    await page.close()

asyncio.run(main())
