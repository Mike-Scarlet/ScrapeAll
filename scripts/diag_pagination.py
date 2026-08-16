
import asyncio, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.cangku.login import CangkuLogin
from scrape_all.sites.cangku import locators
from scrape_all.sites.cangku.consts import CangkuDef
from config import CANGKU_PROXY_SERVER, YEJIANG_USER_ID

# 分页诊断（只读）：轮询记录每页容器出现时间、卡片数量随时间的变化、
# 分页控件 href。只打印数量/时间/URL 等结构信息，不读取页面文本内容。

POLL_INTERVAL = 200      # ms
WATCH_MS = 12000         # 每页最长观察时长


async def diag_page(page, page_no):
  url = f"{CangkuDef.cangku_root_url}/user/{YEJIANG_USER_ID}/post?page={page_no}"
  print(f"\n=== page {page_no}: {url}")
  t0 = time.monotonic()
  await page.goto(url)
  print(f"  goto 返回 +{time.monotonic() - t0:.2f}s  page.url={page.url}")

  card_sel = f"{locators.USER_POST_CONTAINER} {locators.POST_CARD}"
  last_count = -1
  stable_since = None
  container_at = None
  final = None
  while (time.monotonic() - t0) * 1000 < WATCH_MS:
    now = time.monotonic()
    if container_at is None and await page.locator(locators.USER_POST_CONTAINER).count():
      container_at = now - t0
      print(f"  容器出现 +{container_at:.2f}s")
    n = await page.locator(card_sel).count()
    if n != last_count:
      print(f"  +{now - t0:.2f}s  cards={n}")
      last_count, stable_since = n, now
    # 数量稳定（1s 不变）即认为加载完成；满页(12)稳定 0.4s 即可
    if n > 0 and stable_since is not None:
      held = now - stable_since
      if (n >= 12 and held >= 0.4) or held >= 1.0:
        final = n
        break
    await page.wait_for_timeout(POLL_INTERVAL)

  n = final if final is not None else last_count
  print(f"  结论: cards={n}  总耗时 {time.monotonic() - t0:.2f}s")

  # 分页控件的 href（确认站点真实翻页 URL 方案）
  hrefs = await page.eval_on_selector_all(
      "a[href*='page']", "els => els.map(e => e.getAttribute('href'))")
  print(f"  含 page 的链接: {hrefs}")
  return n


async def main():
  async with BrowserSession(CANGKU_PROXY_SERVER) as session:
    await CangkuLogin.GuaranteeCangkuLogin(session.context)
    page = await session.new_page()
    try:
      for page_no in (1, 2, 3):
        await diag_page(page, page_no)
    finally:
      await page.close()

asyncio.run(main())
