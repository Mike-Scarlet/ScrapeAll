
import logging

from playwright.async_api import BrowserContext

from scrape_all.sites.cangku.pages.post_list_page import PostListPage
from scrape_all.sites.cangku.pages.post_page import PostPage

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
    page = await self.context.new_page()
    post_list_page = PostListPage(page)
    post_items = await post_list_page.get_post_links(self.user_id, self.retrieve_page_max)
    await page.close()

    for item in post_items:
      url = item[0]
      title = item[1]
      logging.info(f"start to process {url}, title: {title}")
      await self.ProcessPost(url)

  async def ProcessPost(self, url: str):
    page = await self.context.new_page()
    post_page = PostPage(page)
    try:
      await page.goto(url)

      labels = await post_page.get_labels()
      logging.info(f"labels = {labels}")

      if "动画" not in labels:
        logging.info("post is not animation, skip")
        return

      if not await post_page.has_collapse_card():
        logging.info("no collapse card, skip")
        return

      dl_box_contents = await post_page.parse_collection_dl_boxes()

    finally:
      await page.close()
