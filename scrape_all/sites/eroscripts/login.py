
import logging

from playwright.async_api import BrowserContext
from playwright.async_api import TimeoutError as PWTimeoutError

from scrape_all.sites.eroscripts import locators
from scrape_all.sites.eroscripts.consts import ErosDef


class ErosLogin:
  @staticmethod
  async def GuaranteeErosLogin(context: BrowserContext) -> None:
    """discourse SPA：渲染出 #current-user 即已登录；出现登录按钮则挂住等人工
    在浏览器窗口里登录（cookie 落 browser_session/ 持久 profile）"""
    page = await context.new_page()
    try:
      while True:
        await page.goto(ErosDef.root_url)
        try:
          await page.wait_for_selector(
              f"{locators.CURRENT_USER}, {locators.LOGIN_BUTTON}", timeout=20000)
        except PWTimeoutError:
          logging.warning("登录态检测超时（头像/登录按钮都没渲染出来），重试")
          continue
        if await page.locator(locators.CURRENT_USER).count():
          break
        logging.info("wait for eroscripts login, press enter after login")
        input()
      logging.info("eroscripts login ok")
    finally:
      await page.close()
