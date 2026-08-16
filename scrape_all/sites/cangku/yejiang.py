
from bs4 import BeautifulSoup
import logging, time, re

from playwright.async_api import BrowserContext, Locator

from scrape_all.sites.cangku.consts import CangkuDef
from scrape_all.sites.cangku.user_post import WalkCangkuUserPost

class DLBoxContent:
  def __init__(self):
    self.meta_dict = {}
    self.download_links = {}

  async def ParseFromLocator(self, element: Locator):
    for meta_element in await element.locator('.dl-meta .meta').all():
      key = await meta_element.locator('span').first.get_attribute('class')
      value = await meta_element.text_content()
      self.meta_dict[key] = value.strip()

    dl_link_locator = element.locator('.dl-link')
    for dl_element in await dl_link_locator.locator('.dl-item').all():
      dl_name = await dl_element.text_content()
      on_click_str = await dl_element.get_attribute("onclick")
      find_result = re.findall(r"\('[^']+', '[^']+', '([^']+)'\)", on_click_str)
      if find_result:
        self.download_links[dl_name] = find_result[0]

"""
logic
"""
class YejiangScrab:
  def __init__(self, context: BrowserContext, user_id: str, retrieve_page_max: int = 1):
    self.context = context
    self.user_id = user_id
    self.retrieve_page_max = retrieve_page_max
    self.retrieve_update_time_min = None
    
  async def Run(self):
    walk_cangku_user_post = WalkCangkuUserPost(self.context)
    post_items = await walk_cangku_user_post.GetUserPostLinks(self.user_id, self.retrieve_page_max)
    
    for item in post_items:
      url = item[0]
      title = item[1]
      logging.info(f"start to process {url}, title: {title}")
      await self.ProcessPost(url)

  async def ProcessPost(self, url: str):
    page = await self.context.new_page()

    dl_box_contents = []
    while True:
      await page.goto(url)
    
      label_elements = page.locator('[class="meta-label"]')
      labels = []
      for label_element in await label_elements.all():
        labels.append(await label_element.text_content())
      logging.info(f"labels = {labels}")

      if "动画" not in labels:
        logging.info("post is not animation, skip")
        break

      # find collapse card
      collapse_cards = page.locator('[class="collapse-card"]')
      if await collapse_cards.count() == 0:
        logging.info("no collapse card, skip")
        break      

      for collapse_card in await collapse_cards.all():
        collapse_card_text = await collapse_card.locator('.collapse-btn').first.text_content()
        if "合集" not in collapse_card_text:
          continue

        # parse download box
        for dl_box_element in await collapse_card.locator('.dl-box').all():
          dl_box_content = DLBoxContent()
          await dl_box_content.ParseFromLocator(dl_box_element)
          dl_box_contents.append(dl_box_content)
      break
      
    await page.close()