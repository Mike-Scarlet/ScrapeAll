
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
logging.basicConfig(
    level=logging.NOTSET,
    format="[%(asctime)s] %(message)s",
    # datefmt="[%X]",
)

from playwright.async_api import async_playwright
from scrape_all.browser.context import GetWrapPlaywrightBrowserContext, ProxySettings
from scrape_all.sites.cangku.yejiang import YejiangScrab
from config import CANGKU_PROXY_SERVER, YEJIANG_USER_ID, YEJIANG_PAGE_MAX


async def main():
  async with async_playwright() as p:
    proxy_setting = ProxySettings(server=CANGKU_PROXY_SERVER) if CANGKU_PROXY_SERVER else None

    context = await GetWrapPlaywrightBrowserContext(p, proxy_setting)

    yejiang_scrab = YejiangScrab(context, YEJIANG_USER_ID, YEJIANG_PAGE_MAX)
    get_result = await yejiang_scrab.Run()
    print(get_result)

    print("done")
    input()

    await context.close()

asyncio.run(main())
