
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
import logging
logging.basicConfig(
  level=logging.NOTSET,
  format="[%(asctime)s] %(message)s",
)

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.cangku.login import CangkuLogin
from scrape_all.sites.cangku.store import PostStore
from scrape_all.sites.cangku.yejiang import YejiangCollector
from config import (
  CANGKU_PROXY_SERVER, YEJIANG_USER_ID, YEJIANG_HISTORY_CUTOFF, YEJIANG_PAGE_LIMIT,
)

# collect 阶段入口：登录 -> 翻帖子列表到 cutoff / 已覆盖边界 -> 新帖落库（stat=0，待抓取页面）
# 增量语义：遇到 (url+时间戳) 都已记录的帖子即停；帖子被更新（时间戳变新）则重置重走一遍流程。

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cangku.db")


async def main():
  async with BrowserSession(CANGKU_PROXY_SERVER) as session:
    await CangkuLogin.GuaranteeCangkuLogin(session.context)

    with PostStore(_DB_PATH) as store:
      collector = YejiangCollector(
          session.context, YEJIANG_USER_ID, store,
          YEJIANG_HISTORY_CUTOFF, YEJIANG_PAGE_LIMIT)
      result = await collector.Run()
      pending = store.pending_fetch()

    print(f"\n=== collect done")
    print(f"pages={result.pages} new_posts={result.new_posts} "
          f"updated_posts={result.updated_posts} stop={result.stop_reason}")
    print(f"待抓取帖子页（stat=0）: {len(pending)}")
    print(f"db: {_DB_PATH}")

  try:
    input("\npress enter to exit ")
  except EOFError:
    pass

asyncio.run(main())
