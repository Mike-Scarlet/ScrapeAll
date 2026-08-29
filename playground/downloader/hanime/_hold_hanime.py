# 协同 debug：用与下载引擎一致的画面（同 profile + DOWNLOADER_PROXY + patchright
# stealth）打开该流媒体站页面并停住，每 POLL_S 打一次页面状态变化，窗口保持
# HOLD_S 供人工观察/过验证。顺带打一条 cloudflare trace 出口 IP 供对比。
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.browser.session import BrowserSession
from config import DOWNLOADER_PROXY_SERVER

URL = sys.argv[1] if len(sys.argv) > 1 else "https://hanime1.me/download?v=102424"
HOLD_S = 900        # 停窗观察时长
POLL_S = 5
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_hold_hanime.png")

MARKERS = ("Just a moment", "Attention Required", "Verify you are human",
           "cf-turnstile", "challenge-platform", "__cf_chl", "Enable JavaScript")


async def snapshot(page):
  """(title, 表格行数, 正文头, 命中的 CF 特征)"""
  try:
    title = await page.title()
  except Exception as e:
    title = f"<title err {type(e).__name__}>"
  try:
    rows = await page.evaluate(
        "() => document.querySelectorAll('table.download-table a[data-url]').length")
  except Exception:
    rows = -1
  try:
    body = await page.evaluate(
        "() => document.body ? document.body.innerText.slice(0, 300) : ''")
    body_head = " ".join((body or "").split())[:160]
  except Exception:
    body_head = "<body err>"
  marks = [m for m in MARKERS if m.lower() in (title + " " + body_head).lower()]
  return title, rows, body_head, marks


async def trace_exit(session):
  """同会话下经过代理的 CF trace：出口 IP/机房线索"""
  page = await session.new_page()
  try:
    resp = await page.goto("https://www.cloudflare.com/cdn-cgi/trace",
                           wait_until="domcontentloaded", timeout=20000)
    text = await page.evaluate("() => document.body.innerText")
    keep = {k: v for k, v in (line.split("=", 1) for line in text.splitlines()
                              if "=" in line)
            if k in ("ip", "loc", "colo", "warp")}
    print(f"trace: {keep}（正常浏览器开同地址可对比 ip 是否一致）")
  except Exception as e:
    print(f"trace 失败: {e}")
  finally:
    await page.close()


async def main():
  async with BrowserSession(DOWNLOADER_PROXY_SERVER, stealth=True) as session:
    host = URL.split("/")[2]
    cookies = [c["name"] for c in await session.context.cookies(URL)]
    print(f"profile 里 {host} 既有 cookies: {cookies or '（无）'}")
    await trace_exit(session)

    page = await session.new_page()
    try:
      resp = await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
      print(f"goto -> http={resp.status if resp else 'no-response'} url={page.url}")
    except Exception as e:
      print(f"goto 异常: {type(e).__name__}: {e}")
    print(f"窗口已停住 {HOLD_S}s，请观察（期间可人工点验证，状态变化会打出来）")

    await asyncio.sleep(3)
    cookies = [c["name"] for c in await session.context.cookies(URL)]
    print(f"goto 后 3s cookies: {cookies or '（无）'}")

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
        title, rows, body_head, marks = snap
        print(f"[{time.strftime('%H:%M:%S')}] url={page.url}")
        print(f"    title={title!r} 表格行={rows} CF特征={marks or '无'}")
        print(f"    body: {body_head}")
        last = snap
      await asyncio.sleep(POLL_S)

    try:
      await page.screenshot(path=SHOT)
      print(f"截图已存 {SHOT}")
    except Exception as e:
      print(f"截图失败: {e}")
    cookies = [c["name"] for c in await session.context.cookies(URL)]
    print(f"收尾时 {host} cookies: {cookies or '（无）'}")
    await page.close()


if __name__ == "__main__":
  asyncio.run(main())
