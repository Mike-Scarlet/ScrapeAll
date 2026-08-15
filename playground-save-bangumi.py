
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

links = [
    "https://pan.baidu.com/s/11MdxeBxy70cGuBcBmkGoow?pwd=4bs4",
    "https://pan.baidu.com/s/1ksgRwVjzzZyUSfC_5qevUA?pwd=jd8v",
    "https://pan.baidu.com/s/1CFUAtDroGG-pAh_45CCccQ?pwd=mne7",
    "https://pan.baidu.com/s/1QQYFW6sjvg4WLWztvacFPA?pwd=b4y3",
    "https://pan.baidu.com/s/1Z2LDMt3fcY55Y-ZTpPNWCg?pwd=cd5p",
    "https://pan.baidu.com/s/1xt1qOKuxKj5mQjKZbIuaqQ?pwd=ttcx",
    "https://pan.baidu.com/s/1_rOZwJ72lEezvunwjmqMWg?pwd=g84t",
    "https://pan.baidu.com/s/1BxSpPXTnlmDT_4VIb9wr_g?pwd=115w",
    "https://pan.baidu.com/s/11qUj1qWGivtwk1m1b4Etlg?pwd=vga3",
    "https://pan.baidu.com/s/1i2YQxCKGNhYtUm0msvFung?pwd=dsnh",
    "https://pan.baidu.com/s/1K2rBHVk5OX8svkLzxWDPVg?pwd=9imm",
    "https://pan.baidu.com/s/1qQayAFkyAFnr0RCiHF2kbA?pwd=x6wf",
    "https://pan.baidu.com/s/1i31wSoucBzj6PgCnnns34Q?pwd=s8kn",
    "https://pan.baidu.com/s/1vUg6BqucEuuUgJ-qbo0rFg?pwd=ubwp",
    "https://pan.baidu.com/s/1FWkj8uaWM2omNQAH5Lrcgw?pwd=4r3i",
    "https://pan.baidu.com/s/16u5FAkVshSmhysYhFPEVfw?pwd=ftf6",
    "https://pan.baidu.com/s/1EawS4lzv3kFZf9B3Bvvoyg?pwd=h8ee",
    "https://pan.baidu.com/s/1BVFMWiy5c4j9s_v3TsLonQ?pwd=2cxm",
    "https://pan.baidu.com/s/1LQlAXjyhY-VeAzzKpdiQ6Q?pwd=789b",
    "https://pan.baidu.com/s/1wtOxTjOiOf8xTcIXkuCv0w?pwd=3yp3",
    "https://pan.baidu.com/s/1MMzTYMTuF_dR5xASoZEN6A?pwd=am99",
]

async def main():
  async with async_playwright() as p:
    context = await GetWrapPlaywrightBrowserContext(p)

    # await BaiduPanLogin.GuaranteeBaiduPanLogin(context)
    
    for link in links:
        # baidu_share_url = "https://pan.baidu.com/s/1flqi_JjQRHhCvtN-JJHUJA"
        shared_link_page = await BaiduPanSharedLink.GetSharedLink(context, link)

        saver = SharedLinkSaver(shared_link_page)
        await saver.open_save_dialog()

        nav_result = await saver.navigate_to_path("/bangumi/2510")
        save_result = await saver.confirm_selection()
        
        print(f"save result: {save_result}")
        print("done")
    input()

    await context.close()

asyncio.run(main())