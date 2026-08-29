# 协同 debug 第 2 轮：复现下载腿失败现场并停住。
# 开 download 页 -> 合成 <a href=data-url download> -> Playwright 真点击 ->
# 停窗观察。挂了 hembed CDN 响应监听（状态码/content-type/disposition 都打），
# poller 记录页面 URL/标题/正文变化。你看窗口告诉我下一步。
import asyncio
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.browser.session import BrowserSession
from config import DOWNLOADER_PROXY_SERVER

VID = sys.argv[1] if len(sys.argv) > 1 else "404842"
URL = f"https://hanime1.me/download?v={VID}"
HOLD_S = 1800
POLL_S = 5
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_hold_after_click.png")

MARKERS = ("Just a moment", "Attention Required", "Verify you are human",
           "cf-turnstile", "challenge-platform", "__cf_chl", "Enable JavaScript")

ROWS_JS = """() => Array.from(document.querySelectorAll(
    'table.download-table tr')).map((tr, i) => {
  const a = tr.querySelector('a[data-url]');
  if (!a) return null;
  return {i, url: a.dataset.url || '',
          name: a.getAttribute('download') || '',
          quality: tr.querySelectorAll('td')[1]?.innerText.trim() || ''};
}).filter(Boolean)"""


def best_row(rows):
  def res(q):
    m = re.search(r"(\\d{3,4})\\s*p", q, re.I)
    return int(m.group(1)) if m else -1
  return max(enumerate(rows), key=lambda kv: (res(kv[1]["quality"]), -kv[0]))[1]


async def snapshot(page):
  try:
    title = await page.title()
  except Exception as e:
    title = f"<title err {type(e).__name__}>"
  try:
    body = await page.evaluate(
        "() => document.body ? document.body.innerText.slice(0, 300) : ''")
    body_head = " ".join((body or "").split())[:160]
  except Exception:
    body_head = "<body err>"
  marks = [m for m in MARKERS if m.lower() in (title + " " + body_head).lower()]
  return title, body_head, marks


async def main():
  async with BrowserSession(DOWNLOADER_PROXY_SERVER, stealth=True) as session:
    page = await session.new_page()

    def on_response(r):
      if "hembed.com" in r.url:
        try:
          h = r.headers
          print(f"[resp] {r.status} {r.url.split('?')[0]} "
                f"type={h.get('content-type', '?')} "
                f"disposition={h.get('content-disposition', '无')} "
                f"len={h.get('content-length', '?')}")
        except Exception:
          print(f"[resp] {r.status} {r.url.split('?')[0]} (headers 读不到)")
    page.on("response", on_response)

    resp = await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
    print(f"http={resp.status if resp else '?'} url={page.url}")
    await page.wait_for_selector("table.download-table a[data-url]", timeout=15000)
    await page.wait_for_timeout(1200)
    rows = await page.evaluate(ROWS_JS)
    best = best_row(rows)
    print(f"选档: {best['quality']} name={best['name']!r}")
    print(f"data-url: {best['url']}")

    await page.evaluate("""([url, name]) => {
      const a = document.createElement('a');
      a.id = '__dl_synth';
      a.href = url; a.download = name;
      a.style.cssText = 'position:fixed;left:4px;top:4px;width:8px;height:8px;'
                        + 'opacity:0.01;z-index:2147483647;display:block;';
      document.body.appendChild(a);
      return true;
    }""", [best["url"], best["name"]])
    print("已合成锚点，点击…")
    try:
      async with page.expect_download(timeout=60000) as dl_info:
        await page.locator("#__dl_synth").click()
      dl = await dl_info.value
      print(f"下载事件! suggested={dl.suggested_filename!r}（窗口停住，可人工取消/观察）")
    except Exception as e:
      print(f"无下载事件: {type(e).__name__}")
    await asyncio.sleep(3)
    title, body_head, marks = await snapshot(page)
    print(f"点击后页面: url={page.url}")
    print(f"    title={title!r} CF特征={marks or '无'}")
    print(f"    body: {body_head}")
    print(f"窗口停住 {HOLD_S}s，请观察后告诉我怎么改")

    last = None
    deadline = time.monotonic() + HOLD_S
    while time.monotonic() < deadline:
      try:
        snap = await snapshot(page)
      except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] snapshot 异常 {type(e).__name__}: {e}")
        await asyncio.sleep(POLL_S)
        continue
      if snap != last:
        title, body_head, marks = snap
        print(f"[{time.strftime('%H:%M:%S')}] url={page.url}")
        print(f"    title={title!r} CF特征={marks or '无'}")
        print(f"    body: {body_head}")
        last = snap
      await asyncio.sleep(POLL_S)

    try:
      await page.screenshot(path=SHOT)
      print(f"截图已存 {SHOT}")
    except Exception as e:
      print(f"截图失败: {e}")
    await page.close()


asyncio.run(main())
