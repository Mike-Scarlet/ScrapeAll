
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
import logging
logging.basicConfig(
  level=logging.NOTSET,
  format="[%(asctime)s] %(message)s",
)

from playwright.async_api import TimeoutError as PlaywrightTimeout
try:
  from patchright.async_api import TimeoutError as PatchrightTimeout
  _TIMEOUTS = (PlaywrightTimeout, PatchrightTimeout)
except ImportError:
  _TIMEOUTS = (PlaywrightTimeout,)

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.cangku.login import CangkuLogin
from scrape_all.sites.cangku.pages.post_page import PostPage, post_id, save_post_html
from scrape_all.sites.cangku.store import PostStore
from config import CANGKU_PROXY_SERVER

# fetch 阶段入口：遍历待抓取帖子（stat=0，新到旧），逐帖打开、整页 HTML 落
# data/cangku/posts/{id}.html，stat 0 -> 1（超时 -1）。逐帖提交，中断重跑自动续。

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cangku.db")


async def main():
  with PostStore(_DB_PATH) as store:
    posts = sorted(store.pending_fetch(), key=lambda p: p.post_time, reverse=True)
    print(f"待抓取帖子页（stat=0）: {len(posts)}")
    if not posts:
      return

    ok = fail = 0
    async with BrowserSession(CANGKU_PROXY_SERVER, stealth=True) as session:
      await CangkuLogin.GuaranteeCangkuLogin(session.context)
      page = await session.new_page()
      post_page = PostPage(page)
      try:
        for i, post in enumerate(posts, 1):
          pid = post_id(post.url)
          note = "ok"
          try:
            html = await post_page.fetch_html(post.url)
            save_post_html(pid, html)
            store.mark_fetched(post.url)
            ok += 1
          except _TIMEOUTS:
            store.mark_fetch_failed(post.url)
            fail += 1
            note = "TIMEOUT -> -1"
          print(f"[{i}/{len(posts)}] {pid} {note}")
          await page.wait_for_timeout(500)   # 温和一点
      finally:
        await page.close()

    print(f"\n=== fetch done: ok={ok} fail={fail}")
    print(f"html -> data/cangku/posts/   db -> {_DB_PATH}")

asyncio.run(main())
