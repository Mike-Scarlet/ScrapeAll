

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


driver = GetDefaultSeleniumDriver()

# BaiduPanLogin.GuaranteeBaiduPanLogin(driver)

baidu_share_url = "https://pan.baidu.com/s/1flqi_JjQRHhCvtN-JJHUJA"
BaiduPanSharedLink.GetSharedLink(driver, baidu_share_url, "yezi")

print("current shared link path: ", BaiduPanSharedLinkNavigation.GetCurrentSharedLinkPath(driver))

cslf = BaiduPanSharedLinkNavigation.ListCurrentSharedLinkFiles(driver)
print(cslf)

BaiduPanSharedLinkNavigation.AccessFolder(driver, cslf[0].name)

print("current shared link path: ", BaiduPanSharedLinkNavigation.GetCurrentSharedLinkPath(driver))

cslf = BaiduPanSharedLinkNavigation.ListCurrentSharedLinkFiles(driver)
print(cslf)

BaiduPanSharedLinkNavigation.AccessFolder(driver, "2025")

cslf = BaiduPanSharedLinkNavigation.ListCurrentSharedLinkFiles(driver)
print(cslf)

BaiduPanSharedLinkNavigation.ReturnToPrevFolder(driver)

BaiduPanSharedLinkNavigation.SelectFiles(driver, ["2024", "2025"])


input()

# 等待3秒
time.sleep(3)

# 关闭浏览器
driver.quit()