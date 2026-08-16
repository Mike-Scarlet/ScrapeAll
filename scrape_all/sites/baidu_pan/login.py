
from playwright.async_api import BrowserContext
import logging

class BaiduPanLogin:
  @staticmethod
  async def GuaranteeBaiduPanLogin(context: BrowserContext):
    page = await context.new_page()
    
    while True:
      await page.goto("https://pan.baidu.com/disk/main#/index")
      
      logging.info(f"logging baidu yun, title: {await page.title()}")
      logging.info(f"current url: {page.url}")
    
      if not page.url.startswith("https://pan.baidu.com/login"):
        break

      logging.info("wait for login, press enter after login")
      input()

    logging.info("baidu pan login success")
    await page.close()