
"""pixeldrain 联调：对比「park 停止页」和「自然加载页」上的同源 API fetch。

浏览器窗口里会有两个 tab：
  tab A = 自然加载的 https://pixeldrain.com/u/etStjhv5  —— 请人工观察这页
  tab B = park 在 https://pixeldrain.com/ 根页（window.stop 过）
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

TARGET = "https://pixeldrain.com/u/etStjhv5"
API_FILE = "https://pixeldrain.com/api/file/etStjhv5"

FETCH_JS = """async ({url, timeoutMs}) => {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  const t0 = performance.now();
  try {
    const resp = await fetch(url, {credentials: "include", signal: ctrl.signal,
                                   headers: {Accept: "application/json"}});
    let body = null;
    if (resp.ok) { body = await resp.json(); }
    clearTimeout(timer);
    return {status: resp.status, ms: Math.round(performance.now() - t0),
            body: body ? JSON.stringify(body).slice(0, 300) : null,
            cd: resp.headers.get("content-type")};
  } catch (e) {
    return {status: 0, ms: Math.round(performance.now() - t0),
            error: String(e)};
  }
}"""


async def timed_fetch(page, label, url, timeout_ms=15000):
  t0 = time.monotonic()
  r = await page.evaluate(FETCH_JS, {"url": url, "timeoutMs": timeout_ms})
  wall = time.monotonic() - t0
  print(f"[{label}] {wall:.1f}s -> {r}", flush=True)
  return r


async def main():
  async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
    # tab A：自然加载目标页（不 stop，让它渲染），供人工观察
    obs = await engine.context.new_page()
    resp = await obs.goto(TARGET, wait_until="commit")
    print(f"tab A goto commit: http={resp.status if resp else None} "
          f"final_url={obs.url}", flush=True)
    # 等渲染稳定
    try:
      await obs.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception as e:
      print(f"tab A domcontentloaded 超时: {e}", flush=True)
    print(f"tab A 现在的 url={obs.url} title={await obs.title()!r}", flush=True)

    # tab B：现行实现——park 根页 + stop
    parked, lock = await engine._page_for(API_FILE, park_url="https://pixeldrain.com/")
    async with lock:
      print(f"tab B parked url={parked.url} readyState="
            f"{await parked.evaluate('document.readyState')}", flush=True)

      await timed_fetch(parked, "B1 park页 api/file/etStjhv5", API_FILE)
      await timed_fetch(parked, "B2 park页 api/list/x2CLfTjy",
                        "https://pixeldrain.com/api/list/x2CLfTjy")
      await timed_fetch(parked, "B3 park页 api/file/kV6Aqw71",
                        "https://pixeldrain.com/api/file/kV6Aqw71")

    # 对照：从自然加载的 tab A 发同样的请求
    await timed_fetch(obs, "A1 自然页 api/file/etStjhv5", API_FILE)
    await timed_fetch(obs, "A2 自然页 api/list/x2CLfTjy",
                      "https://pixeldrain.com/api/list/x2CLfTjy")

    print("\n浏览器保持打开 180s，请在窗口里观察两个 tab 后告诉我各自显示什么", flush=True)
    await asyncio.sleep(180)


asyncio.run(main())
