
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
logging.basicConfig(
  level=logging.NOTSET,
  format="[%(asctime)s] %(message)s",
)

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.baidu_pan.errors import BaiduPanError
from scrape_all.sites.baidu_pan.pages.shared_link_page import SharedLinkPage, SELECT_NONE
from scrape_all.sites.baidu_pan.pages.save_dialog import SaveDialog
from config import BAIDU_PAN_PROXY_SERVER, WALK_LINKS

# 只读预检：把转存链路完整走一遍但绝不落盘 ——
# 不点确认保存、不新建文件夹（create_if_missing=False），结束还原勾选状态

SOURCE_DIR = "/Mimu/2025"
NAMES = ["25.08", "25.09"]
NAV_TARGET = "/"          # 只导航到必然存在的根目录


async def main():
  async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
    link = WALK_LINKS[0]
    link_page = await SharedLinkPage.open(session.context, link)

    await link_page.goto_path(SOURCE_DIR)
    entries = await link_page.list_files()
    print("folder entries:", [(e.name, e.is_dir, e.is_selected) for e in entries])

    await link_page.select_files(NAMES)
    entries = await link_page.list_files()
    picked = {e.name: e.is_selected for e in entries}
    print("after select:", {n: picked.get(n) for n in NAMES})
    assert all(picked.get(n) for n in NAMES), "select_files 没有勾上目标条目"

    dialog = SaveDialog(link_page.page)
    await dialog.open()
    ok, msg = await dialog.navigate_to(NAV_TARGET, create_if_missing=False)
    print(f"navigate_to({NAV_TARGET!r}): ok={ok} msg={msg}")

    await dialog.cancel()
    await link_page.multi_select_to(SELECT_NONE)   # 还原现场
    await link_page.page.close()
    print("verify chain done (no save clicked)")

asyncio.run(main())
