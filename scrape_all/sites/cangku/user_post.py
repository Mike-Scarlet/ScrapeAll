
import logging
from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext
from scrape_all.sites.cangku.consts import CangkuDef

class WalkCangkuUserPost:
  def __init__(self, context: BrowserContext):
    self.context = context
  
  async def GetUserPostLinks(self, user_id: str, till_page: int) -> list[tuple[str, str]]:
    result = []
    
    new_page = await self.context.new_page()

    for i in range(1, till_page + 1):
      url = f"{CangkuDef.cangku_root_url}/user/{user_id}/post?page={i}"
      await new_page.goto(url)
      
      await new_page.wait_for_selector(".post-card.simple-post-card", timeout=10000)
      await new_page.wait_for_timeout(200)
      user_post_element = await new_page.wait_for_selector("#user-post", timeout=10000)
      user_post_html = await user_post_element.evaluate("el => el.outerHTML")
      
      soup = BeautifulSoup(user_post_html, "lxml")
      
      soup_all_href = soup.find_all("a", href=True)
      for soup_a in soup_all_href:
        full_url = f"{CangkuDef.cangku_root_url}{soup_a['href']}"
        title = soup_a["title"]
        result.append((full_url, title))
    
    await new_page.close()
    return result