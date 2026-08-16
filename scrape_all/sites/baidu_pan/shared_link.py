
import logging
import asyncio
from playwright.async_api import BrowserContext, Page
from scrape_all.sites.baidu_pan.predicates import WaitForBaidupanSharedLinkStable
  
class BaiduPanSharedLink:
  @staticmethod
  async def IsInRequirePasswordPage(page: Page) -> bool:
    return "请输入提取码" in await page.title()

  @staticmethod
  async def GetSharedLink(context: BrowserContext, shared_link_url: str, password: str = None) -> str:
    """
    get baidu pan shared link
    
    returns:
      the page if no error
      otherwise, error message
    """
    page = None
    try:
      logging.info(f"> getting shared link: {shared_link_url}")

      page = await context.new_page()
      await page.goto(shared_link_url)
      await page.wait_for_load_state("domcontentloaded")
      # await page.wait_for_load_state("load")
      
      if shared_link_url[-8:-4] == "pwd=":
        logging.info(f"has pwd in link, do wait for a while")
        await asyncio.sleep(5)

      if await BaiduPanSharedLink.IsInRequirePasswordPage(page):
        if password is None:
          logging.error("need password")
          return "need password"
        if len(password) != 4:
          logging.error("password length must be 4")
          return "password length must be 4"
        
        access_code_input = page.locator("#accessCode")
        await access_code_input.fill(password)
        
        submit_button = page.locator("#submitBtn")
        await submit_button.click()
        
        await WaitForBaidupanSharedLinkStable(page)
      
      if await BaiduPanSharedLink.IsInRequirePasswordPage(page):
        logging.error("password error")
        return "password error"
      
      logging.info(f"< get shared link: {shared_link_url} success")
      return page
      
    except Exception as e:
      logging.error(f"get shared link failed: {e}")
      if page:
        await page.close()

      return f"get shared link failed: {e}"
    