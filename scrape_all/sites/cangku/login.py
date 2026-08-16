
import logging
from playwright.async_api import BrowserContext, Page
from scrape_all.sites.cangku.consts import CangkuDef

class CangkuLogin:
  @staticmethod
  async def GuaranteeCangkuLogin(context: BrowserContext) -> Page:
    page = await context.new_page()
    
    while True:
      await page.goto(CangkuDef.cangku_root_url)
      
      logging.info(f"logging cangku, title: {await page.title()}")
      logging.info(f"current url: {page.url}")
    
      if not page.url.startswith(f"{CangkuDef.cangku_root_url}/login"):
        break

      logging.info("wait for login, press enter after login")
      input()  # 使用阻塞式input，符合原有逻辑

    logging.info("login success")
    await page.close()