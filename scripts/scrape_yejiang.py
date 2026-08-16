
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
logging.basicConfig(
    level=logging.NOTSET,
    format="[%(asctime)s] %(message)s",
    # datefmt="[%X]",
)

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.cangku.yejiang import YejiangScrab
from config import CANGKU_PROXY_SERVER, YEJIANG_USER_ID, YEJIANG_PAGE_MAX


async def main():
  async with BrowserSession(CANGKU_PROXY_SERVER) as session:
    yejiang_scrab = YejiangScrab(session.context, YEJIANG_USER_ID, YEJIANG_PAGE_MAX)
    get_result = await yejiang_scrab.Run()
    print(get_result)

    print("done")
    input()

asyncio.run(main())
