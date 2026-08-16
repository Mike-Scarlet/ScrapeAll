

import time, sys, os

from python_general_lib.environment_setup.logging_setup import *
logging.basicConfig(
    level=logging.NOTSET,
    format="[%(asctime)s] %(message)s",
    # datefmt="[%X]",
)

from scrab_browser.selenium_driver_retrieve import GetDefaultSeleniumDriver
from scrab_browser.websites.baidu_pan.login import BaiduPanLogin
from scrab_browser.websites.baidu_pan.get_shared_link import BaiduPanSharedLink
from scrab_browser.websites.baidu_pan.shared_link_navigation import BaiduPanSharedLinkNavigation
from scrab_browser.websites.baidu_pan.shared_link_saver import SharedLinkSaver

driver = GetDefaultSeleniumDriver()

# BaiduPanLogin.GuaranteeBaiduPanLogin(driver)

baidu_share_url = "https://pan.baidu.com/s/1flqi_JjQRHhCvtN-JJHUJA"
BaiduPanSharedLink.GetSharedLink(driver, baidu_share_url, "yezi")

saver = SharedLinkSaver(driver)
saver.open_save_dialog()

nav_result = saver.navigate_to_path("/扒/test/test1")
# if nav_result[0]:
#     save_stat = saver.confirm_selection()
#     print(save_stat)

input()

# 等待3秒
time.sleep(3)

# 关闭浏览器
driver.quit()