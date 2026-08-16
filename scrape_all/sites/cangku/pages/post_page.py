
import re
from playwright.async_api import Locator, Page

from scrape_all.sites.cangku import locators

class DLBoxContent:
  def __init__(self):
    self.meta_dict = {}
    self.download_links = {}

  async def ParseFromLocator(self, element: Locator):
    for meta_element in await element.locator(locators.DL_META_ITEM).all():
      key = await meta_element.locator('span').first.get_attribute('class')
      value = await meta_element.text_content()
      self.meta_dict[key] = value.strip()

    dl_link_locator = element.locator(locators.DL_LINK_LIST)
    for dl_element in await dl_link_locator.locator(locators.DL_ITEM).all():
      dl_name = await dl_element.text_content()
      on_click_str = await dl_element.get_attribute("onclick")
      find_result = re.findall(r"\('[^']+', '[^']+', '([^']+)'\)", on_click_str)
      if find_result:
        self.download_links[dl_name] = find_result[0]

class PostPage:
  def __init__(self, page: Page):
    self.page = page

  async def get_labels(self) -> list[str]:
    labels = []
    for label_element in await self.page.locator(locators.META_LABEL).all():
      labels.append(await label_element.text_content())
    return labels

  async def has_collapse_card(self) -> bool:
    return await self.page.locator(locators.COLLAPSE_CARD).count() > 0

  async def parse_collection_dl_boxes(self) -> list[DLBoxContent]:
    dl_box_contents = []
    for collapse_card in await self.page.locator(locators.COLLAPSE_CARD).all():
      collapse_card_text = await collapse_card.locator(locators.COLLAPSE_BTN).first.text_content()
      if "合集" not in collapse_card_text:
        continue

      # parse download box
      for dl_box_element in await collapse_card.locator(locators.DL_BOX).all():
        dl_box_content = DLBoxContent()
        await dl_box_content.ParseFromLocator(dl_box_element)
        dl_box_contents.append(dl_box_content)
    return dl_box_contents
