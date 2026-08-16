
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
logging.basicConfig(
    level=logging.NOTSET,
    format="[%(asctime)s] %(message)s",
    # datefmt="[%X]",
)

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.baidu_pan.login import BaiduPanLogin
from scrape_all.sites.baidu_pan.errors import BaiduPanError
from scrape_all.sites.baidu_pan.pages.shared_link_page import SharedLinkPage
from scrape_all.sites.baidu_pan.pages.save_dialog import SaveDialog
from config import BAIDU_PAN_PROXY_SERVER, BAIDU_SAVE_TARGET_PATH, BANGUMI_LINKS


async def main():
  async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
    # await BaiduPanLogin.GuaranteeBaiduPanLogin(session.context)

    for link in BANGUMI_LINKS:
      try:
        shared_link_page = await SharedLinkPage.open(session.context, link)
      except BaiduPanError as e:
        logging.error(f"skip link {link}: {e}")
        continue

      saver = SaveDialog(shared_link_page.page)
      await saver.open()

      nav_result = await saver.navigate_to(BAIDU_SAVE_TARGET_PATH)
      save_result = await saver.confirm()

      print(f"save result: {save_result}")
      print("done")
    input()

asyncio.run(main())
