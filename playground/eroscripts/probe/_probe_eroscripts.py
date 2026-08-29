import asyncio, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from playwright.async_api import TimeoutError as PWTimeout

from scrape_all.browser.session import BrowserSession

URL = "https://discuss.eroscripts.com/tag/loli/68"

async def settle(page, timeout_s: float = 20):
  """等页面稳定：轮询 topic 行数，数量连续 1.5s 不变且 >0 即认为稳定"""
  sel = "table.topic-list tbody tr"
  deadline = time.monotonic() + timeout_s
  last, stable_since = -1, None
  while time.monotonic() < deadline:
    n = await page.locator(sel).count()
    now = time.monotonic()
    if n != last:
      last, stable_since = n, now
    if n > 0 and now - stable_since >= 1.5:
      return n
    await page.wait_for_timeout(250)
  return last

async def main():
  async with BrowserSession() as session:
    page = await session.new_page()
    resp = await page.goto(URL, timeout=60000)
    print("status:", resp.status if resp else None)
    await page.wait_for_load_state("domcontentloaded")

    n = await settle(page)
    print("title:", await page.title())
    print("url:", page.url)
    print(f"topic rows settled: {n}")

    avatar = await page.locator("#current-user").count()
    login_btn = await page.locator(".login-button").count()
    print(f"avatar={avatar} login_button={login_btn}")

    for sel in ("#list-area", ".topic-list", ".topic-list-item",
                ".tag-list", ".latest-topic-list-item"):
      print(f"count {sel!r}: {await page.locator(sel).count()}")

    row = page.locator("table.topic-list tbody tr").first
    if await row.count():
      html = await row.evaluate("el => el.outerHTML")
      print("--- first row html ---")
      print(html[:5000])

    thead = await page.locator("table.topic-list thead").count()
    if thead:
      print("--- thead ---")
      print(await page.locator("table.topic-list thead").evaluate("el => el.innerText"))

    # 分页 / 加载更多机制：页脚有没有 more 链接
    for sel in (".topic-list-bottom .footer-message", "a[rel='next']", ".more-topics-link"):
      print(f"count {sel!r}: {await page.locator(sel).count()}")
    print("--- footer text ---")
    footer = page.locator("table.topic-list tbody tr:last-child")
    if await footer.count():
      print((await footer.evaluate("el => el.innerText"))[:300])

    await page.screenshot(path="data/_probe_ero_tag.png", full_page=False)
    print("screenshot saved")
    await page.close()

asyncio.run(main())
