
"""pixeldrain 联调 v2：定位 API body 卡死范围 + 验证浏览器下载主链路。

实验：
  1) 自然加载 /u/etStjhv5（已知活），从页内流式读 /api/file/etStjhv5 的 body
     —— 字节时间线：完全不动 vs 缓慢滴
  2) Range:0-0 只读头（API 和 ?download 两个 URL）—— 头能不能到
  3) goto /api/file/etStjhv5?download 触发浏览器下载事件，拿到文件名即 cancel
     —— 真正的下载主链路是否可用
  4) 自然加载一个 /l/ 列表页，看渲染出来的标题（列表页是否依赖卡死的 API）
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

FILE_ID = "etStjhv5"
TARGET = f"https://pixeldrain.com/u/{FILE_ID}"
API = f"https://pixeldrain.com/api/file/{FILE_ID}"
DL = f"{API}?download"

STREAM_JS = """async ({url, budgetMs}) => {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), budgetMs);
  const t0 = performance.now();
  try {
    const resp = await fetch(url, {credentials: "include", signal: ctrl.signal});
    const head = {status: resp.status, ms: Math.round(performance.now() - t0),
                  ct: resp.headers.get("content-type"),
                  cl: resp.headers.get("content-length")};
    if (!resp.ok) { clearTimeout(timer); return {head}; }
    const reader = resp.body.getReader();
    const chunks = [];
    let total = 0;
    while (total < 4000 && chunks.length < 50) {
      const {done, value} = await reader.read();
      if (done) break;
      chunks.push({at_ms: Math.round(performance.now() - t0), n: value.length});
      total += value.length;
    }
    clearTimeout(timer);
    ctrl.abort();
    return {head, chunks, total};
  } catch (e) {
    return {error: String(e), at_ms: Math.round(performance.now() - t0)};
  }
}"""

RANGE_JS = """async ({url, timeoutMs}) => {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  const t0 = performance.now();
  try {
    const resp = await fetch(url, {credentials: "include", signal: ctrl.signal,
                                   headers: {Range: "bytes=0-0"}});
    const h = {};
    resp.headers.forEach((v, k) => h[k] = v);
    clearTimeout(timer);
    ctrl.abort();
    return {status: resp.status, ms: Math.round(performance.now() - t0), headers: h};
  } catch (e) { return {status: 0, ms: Math.round(performance.now() - t0),
                        error: String(e)}; }
}"""


async def main():
  async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
    page = await engine.context.new_page()
    resp = await page.goto(TARGET, wait_until="commit")
    print(f"[1] /u/ 页 commit http={resp.status if resp else None}", flush=True)
    try:
      await page.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
      pass
    print(f"[1] /u/ 页 title={await page.title()!r}", flush=True)

    r = await page.evaluate(STREAM_JS, {"url": API, "budgetMs": 12000})
    print(f"[2] API 流式读: {r}", flush=True)

    for label, url in [("API", API), ("DL", DL)]:
      r = await page.evaluate(RANGE_JS, {"url": url, "timeoutMs": 10000})
      print(f"[3] Range 头 {label}: {r}", flush=True)

    print("[4] 触发浏览器下载（拿到事件即 cancel，不拉数据）...", flush=True)
    try:
      async with page.expect_download(timeout=30000) as dl_info:
        try:
          await page.goto(DL)
        except Exception as e:
          if "ERR_ABORTED" not in str(e):
            raise
      download = await dl_info.value
      print(f"[4] 下载事件 OK: suggested={download.suggested_filename!r}", flush=True)
      await download.cancel()
    except Exception as e:
      print(f"[4] 下载事件失败: {e}", flush=True)

    # 列表页渲染验证：找一个库内 /l/ 链接自然加载看标题
    import json, sqlite3
    con = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "data", "eroscripts.db"))
    llinks = []
    for (lj,) in con.execute(
        "SELECT links_json FROM EroTopicItem WHERE stat=2"):
      for l in json.loads(lj):
        if "/l/" in l["url"] and l["url"] not in llinks:
          llinks.append(l["url"])
      if len(llinks) >= 3:
        break
    con.close()
    for u in llinks[:2]:
      p2 = await engine.context.new_page()
      try:
        r2 = await p2.goto(u, wait_until="domcontentloaded", timeout=25000)
        await p2.wait_for_timeout(3000)   # 给客户端渲染留时间
        print(f"[5] {u} -> http={r2.status if r2 else None} "
              f"title={await p2.title()!r}", flush=True)
      except Exception as e:
        print(f"[5] {u} -> 失败 {e}", flush=True)
      finally:
        await p2.close()

    print("\n浏览器再保持 60s 供观察", flush=True)
    await asyncio.sleep(60)


asyncio.run(main())
