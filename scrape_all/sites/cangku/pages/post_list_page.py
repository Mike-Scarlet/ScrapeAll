
from bs4 import BeautifulSoup
from playwright.async_api import Page

from scrape_all.sites.cangku import locators
from scrape_all.sites.cangku.consts import CangkuDef

class PostListPage:
  def __init__(self, page: Page):
    self.page = page

  async def get_post_links(self, user_id: str, till_page: int) -> list[tuple[str, str]]:
    result = []

    for i in range(1, till_page + 1):
      url = f"{CangkuDef.cangku_root_url}/user/{user_id}/post?page={i}"
      await self.page.goto(url)

      await self.page.wait_for_selector(locators.POST_CARD, timeout=10000)
      await self.page.wait_for_timeout(200)
      user_post_element = await self.page.wait_for_selector(locators.USER_POST_CONTAINER, timeout=10000)
      user_post_html = await user_post_element.evaluate("el => el.outerHTML")

      soup = BeautifulSoup(user_post_html, "lxml")

      soup_all_href = soup.find_all("a", href=True)
      for soup_a in soup_all_href:
        full_url = f"{CangkuDef.cangku_root_url}{soup_a['href']}"
        title = soup_a["title"]
        result.append((full_url, title))

    return result
