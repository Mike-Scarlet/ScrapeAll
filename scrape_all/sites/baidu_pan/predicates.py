
from playwright.async_api import Page

from scrape_all.sites.baidu_pan import locators

async def WaitForBaidupanSharedLinkStable(page: Page, timeout: int = 10000):
  await page.wait_for_selector(locators.SHARED_LINK_STABLE_SELECTOR, state='visible', timeout=timeout)
