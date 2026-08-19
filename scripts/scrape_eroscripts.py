
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
import logging
logging.basicConfig(
  level=logging.NOTSET,
  format="[%(asctime)s] %(message)s",
)

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.eroscripts.collector import TagCollector
from scrape_all.sites.eroscripts.login import ErosLogin
from scrape_all.sites.eroscripts.store import TopicStore
from config import EROS_PROXY_SERVER, EROS_TAG_URL, EROS_HISTORY_CUTOFF, EROS_PAGE_LIMIT

# collect 阶段入口：登录 -> 沿 bumped_at 翻 tag 列表到 cutoff / 已覆盖边界
# -> 新帖落库（stat=0，待抓取 topic 页）。增量语义：遇 (topic_id+bumped_at)
# 都已记录的帖子即停；帖子被顶起（bumped_at 变新）则重置重走一遍流程。

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "eroscripts.db")


async def main():
  async with BrowserSession(EROS_PROXY_SERVER) as session:
    await ErosLogin.GuaranteeErosLogin(session.context)

    with TopicStore(_DB_PATH) as store:
      collector = TagCollector(
          session.context, EROS_TAG_URL, store,
          EROS_HISTORY_CUTOFF, EROS_PAGE_LIMIT)
      result = await collector.Run()
      pending = store.pending_fetch()

    print(f"\n=== collect done")
    print(f"pages={result.pages} new_topics={result.new_topics} "
          f"updated_topics={result.updated_topics} stop={result.stop_reason}")
    print(f"待抓取 topic 页（stat=0）: {len(pending)}")
    print(f"db: {_DB_PATH}")

  try:
    input("\npress enter to exit ")
  except EOFError:
    pass

asyncio.run(main())
