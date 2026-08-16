
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
logging.basicConfig(
    level=logging.NOTSET,
    format="[%(asctime)s] %(message)s",
    # datefmt="[%X]",
)

from playwright.async_api import async_playwright
from scrape_all.browser.session import BrowserSession
from scrape_all.sites.baidu_pan.login import BaiduPanLogin
from scrape_all.sites.baidu_pan.shared_link import BaiduPanSharedLink
from scrape_all.sites.baidu_pan.saver import SharedLinkSaver
from config import BAIDU_PAN_PROXY_SERVER, BAIDU_SAVE_TARGET_PATH, BANGUMI_LINKS


async def main():
  async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
    # await BaiduPanLogin.GuaranteeBaiduPanLogin(session.context)

    for link in BANGUMI_LINKS:
        shared_link_page = await BaiduPanSharedLink.GetSharedLink(session.context, link)

        saver = SharedLinkSaver(shared_link_page)
        await saver.open_save_dialog()

        nav_result = await saver.navigate_to_path(BAIDU_SAVE_TARGET_PATH)
        save_result = await saver.confirm_selection()

        print(f"save result: {save_result}")
        print("done")
    input()

asyncio.run(main())
