

import time, sys, os

from python_general_lib.environment_setup.logging_setup import *
logging.basicConfig(
    level=logging.NOTSET,
    format="[%(asctime)s] %(message)s",
    # datefmt="[%X]",
)

from scrab_browser.selenium_driver_retrieve import GetDefaultSeleniumDriver
# from scrab_browser.websites.baidu_pan.login import BaiduPanLogin
# from scrab_browser.websites.baidu_pan.get_shared_link import BaiduPanSharedLink
# from scrab_browser.websites.baidu_pan.shared_link_navigation import BaiduPanSharedLinkNavigation
# from scrab_browser.websites.baidu_pan.shared_link_saver import SharedLinkSaver
from scrab_browser.websites.cangku.login import CangkuLogin
from scrab_browser.websites.cangku.walk_cangku_user_post import WalkCangkuUserPost

driver = GetDefaultSeleniumDriver()

# CangkuLogin.GuaranteeCangkuLogin(driver)

walk_cangku_user_post = WalkCangkuUserPost(driver)
walk_cangku_user_post.GetUserPostLinks("309550", 2)

input()

# 等待3秒
time.sleep(3)

# 关闭浏览器
driver.quit()