
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
# from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright

async def main():
  async with async_playwright() as p:
    context = await GetWrapPlaywrightBrowserContext(p)

    # await BaiduPanLogin.GuaranteeBaiduPanLogin(context)

    baidu_share_url = "https://pan.baidu.com/s/1flqi_JjQRHhCvtN-JJHUJA"
    shared_link_page = await BaiduPanSharedLink.GetSharedLink(
        context, baidu_share_url, "yezi")

    cslf = await BaiduPanSharedLinkNavigation.ListCurrentSharedLinkFiles(shared_link_page)
    print(cslf)

    await BaiduPanSharedLinkNavigation.AccessFolder(shared_link_page, cslf[0].name)

    print("current shared link path: ", await BaiduPanSharedLinkNavigation.GetCurrentSharedLinkPath(shared_link_page))

    cslf = await BaiduPanSharedLinkNavigation.ListCurrentSharedLinkFiles(shared_link_page)
    print(cslf)

    await BaiduPanSharedLinkNavigation.AccessFolder(shared_link_page, "2025")

    cslf = await BaiduPanSharedLinkNavigation.ListCurrentSharedLinkFiles(shared_link_page)
    print(cslf)

    await BaiduPanSharedLinkNavigation.ReturnToPrevFolder(shared_link_page)

    await BaiduPanSharedLinkNavigation.SelectFiles(shared_link_page, ["2024", "2025"])

    input()

    await context.close()

asyncio.run(main())