

import asyncio, os

from python_general_lib.environment_setup.logging_setup import *
logging.basicConfig(
    level=logging.NOTSET,
    format="[%(asctime)s] %(message)s",
    # datefmt="[%X]",
)

from playwright.async_api import async_playwright
from scrab_browser.playwright_browser_retrieve import GetWrapPlaywrightBrowserContext, ProxySettings
from scrab_browser.websites.cangku.login import CangkuLogin
from scrab_browser.websites.cangku.walk_cangku_user_post import WalkCangkuUserPost


async def main():
  async with async_playwright() as p:
    proxy_setting = ProxySettings(
        server="http://127.0.0.1:2080",
    )

    context = await GetWrapPlaywrightBrowserContext(p, proxy_setting)

    # page = await CangkuLogin.GuaranteeCangkuLogin(context)

    walk_cangku_user_post = WalkCangkuUserPost(context)
    get_result = await walk_cangku_user_post.GetUserPostLinks("309550", 2)
    print(get_result)

    print("done")
    input()

    await context.close()

asyncio.run(main())
