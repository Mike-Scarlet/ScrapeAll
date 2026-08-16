
import asyncio, os

from python_general_lib.environment_setup.logging_setup import *
logging.basicConfig(
    level=logging.NOTSET,
    format="[%(asctime)s] %(message)s",
    # datefmt="[%X]",
)

from scrab_browser.playwright_browser_retrieve import GetWrapPlaywrightBrowserContext
from scrab_browser.websites.baidu_pan.login import BaiduPanLogin
from scrab_browser.websites.baidu_pan.get_shared_link import BaiduPanSharedLink
from scrab_browser.websites.baidu_pan.shared_link_navigation import BaiduPanSharedLinkNavigation
from scrab_browser.websites.baidu_pan.shared_link_saver import SharedLinkSaver
# from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright

async def main():
  async with async_playwright() as p:
    context = await GetWrapPlaywrightBrowserContext(p)

    # await BaiduPanLogin.GuaranteeBaiduPanLogin(context)

    baidu_share_url = "https://pan.baidu.com/s/1flqi_JjQRHhCvtN-JJHUJA"
    shared_link_page = await BaiduPanSharedLink.GetSharedLink(
        context, baidu_share_url, "yezi")

    saver = SharedLinkSaver(shared_link_page)
    await saver.open_save_dialog()

    nav_result = await saver.navigate_to_path("/扒/test/test1")
    save_result = await saver.confirm_selection()
    
    print(f"save result: {save_result}")
    print("done")
    input()

    await context.close()

asyncio.run(main())