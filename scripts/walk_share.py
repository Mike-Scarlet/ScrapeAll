
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
logging.basicConfig(
  level=logging.NOTSET,
  format="[%(asctime)s] %(message)s",
)

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.baidu_pan.errors import BaiduPanError
from scrape_all.sites.baidu_pan.pages.shared_link_page import SharedLinkPage
from scrape_all.sites.baidu_pan.walker import ShareWalker
from scrape_all.sites.baidu_pan.tree import chain, skip, stop_below, format_tree
from config import BAIDU_PAN_PROXY_SERVER, WALK_LINKS

# 只读脚本：遍历分享目录树并打印，不做任何选择/转存
POLICY = chain(
  skip("保存资源自動領取優惠卷*"),   # 每个分享里都有的广告文件夹
  stop_below("20*"),                # 20* 目录（2025/2026）只展开一级：月份目录作为整体单元
)


async def main():
  async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
    for link in WALK_LINKS:
      try:
        shared_link_page = await SharedLinkPage.open(session.context, link)
      except BaiduPanError as e:
        logging.error(f"skip link {link}: {e}")
        continue

      try:
        tree = await ShareWalker(shared_link_page).walk(POLICY)
      except BaiduPanError as e:
        logging.error(f"walk failed {link}: {e}")
        continue
      finally:
        await shared_link_page.page.close()

      print(f"\n=== {link}")
      print(format_tree(tree))

    try:
      input("\ndone, press enter to close browser ")
    except EOFError:
      pass

asyncio.run(main())
