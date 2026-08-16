
import asyncio
import logging
from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext, Page

from scrape_all.sites.baidu_pan import locators
from scrape_all.sites.baidu_pan.errors import BaiduPanError
from scrape_all.sites.baidu_pan.predicates import WaitForBaidupanSharedLinkStable

SELECT_ALL = "all"
SELECT_PART = "part"
SELECT_NONE = "none"

class BaiduPanEntry:
  def __init__(self):
    self.name = None
    self.is_dir = False
    self.is_selected = False

  def __repr__(self):
    return f"BaiduPanEntry(name={self.name}, is_dir={self.is_dir}, is_selected={self.is_selected})"

class SharedLinkPage:
  def __init__(self, page: Page):
    self.page = page

  @staticmethod
  async def open(context: BrowserContext, shared_link_url: str, password: str = None) -> "SharedLinkPage":
    """
    open a baidu pan shared link page, fill password if needed

    raise BaiduPanError on failure
    """
    page = None
    try:
      logging.info(f"> getting shared link: {shared_link_url}")

      page = await context.new_page()
      await page.goto(shared_link_url)
      await page.wait_for_load_state("domcontentloaded")

      if shared_link_url[-8:-4] == "pwd=":
        logging.info("has pwd in link, do wait for a while")
        await asyncio.sleep(5)

      if await SharedLinkPage.IsInRequirePasswordPage(page):
        if password is None:
          raise BaiduPanError("need password")
        if len(password) != 4:
          raise BaiduPanError("password length must be 4")

        await page.locator(locators.ACCESS_CODE_INPUT).fill(password)
        await page.locator(locators.SUBMIT_BTN).click()

        await WaitForBaidupanSharedLinkStable(page)

      if await SharedLinkPage.IsInRequirePasswordPage(page):
        raise BaiduPanError("password error")

      logging.info(f"< get shared link: {shared_link_url} success")
      return SharedLinkPage(page)

    except BaiduPanError:
      if page is not None:
        await page.close()
      raise
    except Exception as e:
      logging.error(f"get shared link failed: {e}")
      if page is not None:
        await page.close()
      raise BaiduPanError(f"get shared link failed: {e}") from e

  @staticmethod
  async def IsInRequirePasswordPage(page: Page) -> bool:
    return locators.REQUIRE_PASSWORD_TITLE in await page.title()

  @staticmethod
  async def IsInSharedLinkPage(page: Page) -> bool:
    return locators.SITE_NAME in await page.title()

  async def get_current_path(self) -> str:
    if not await SharedLinkPage.IsInSharedLinkPage(self.page):
      raise BaiduPanError("not in shared link page")

    await WaitForBaidupanSharedLinkStable(self.page)

    path_holder_element = self.page.locator(locators.BREADCRUMB_HOLDER).first
    style_value = await path_holder_element.get_attribute("style")
    if style_value and "none" in style_value:
      return "/"   # root path

    full_path_element = self.page.locator(locators.BREADCRUMB_FULL_PATH).first
    path_text = await full_path_element.text_content()
    if path_text:
      path_text = path_text.replace(">", "/")
      return path_text.removeprefix("全部文件")

    return "/"

  async def list_files(self) -> list[BaiduPanEntry]:
    if not await SharedLinkPage.IsInSharedLinkPage(self.page):
      raise BaiduPanError("not in shared link page")

    await WaitForBaidupanSharedLinkStable(self.page)

    folder_content_element = self.page.locator(locators.FOLDER_CONTENT).first
    content_html = await folder_content_element.evaluate("el => el.outerHTML")
    soup = BeautifulSoup(content_html, "lxml")

    all_dds = soup.find_all("dd")
    result = []
    for dd in all_dds:
      is_selected = locators.ITEM_SELECTED_CLASS in dd.attrs["class"]

      content_name = dd.find(class_="filename").attrs["title"]
      file_icon_soup = dd.find(class_=locators.FILE_ICON_CLASS)
      is_dir = False
      for attr in file_icon_soup.attrs["class"]:
        if locators.DIR_CLASS_MARKER in attr:
          is_dir = True
          break

      ent = BaiduPanEntry()
      ent.name = content_name
      ent.is_dir = is_dir
      ent.is_selected = is_selected
      result.append(ent)
    return result

  async def access_folder(self, folder_name: str):
    folder_locator = self.page.locator(locators.file_link(folder_name)).first
    await folder_locator.wait_for(state="visible")
    await folder_locator.click()

    await WaitForBaidupanSharedLinkStable(self.page)
    await self.page.wait_for_timeout(500)

  async def return_to_prev_folder(self) -> bool:
    try:
      return_locator = self.page.get_by_text(locators.RETURN_TO_PREV_TEXT).first
      await return_locator.wait_for(state="visible")
      await return_locator.click()

      await WaitForBaidupanSharedLinkStable(self.page)
      return True
    except Exception as e:
      logging.error(f"return to prev folder failed: {e}")
      return False

  async def multi_select_to(self, select_status: str):
    """
    select_status: accept [all, none]
    """
    if select_status not in (SELECT_NONE, SELECT_ALL):
      raise BaiduPanError("invalid select status")

    list_entries = await self.list_files()
    current_select_status = SharedLinkPage.GetCurrentMultiSelectStatus(list_entries)

    if current_select_status == select_status:
      return

    display_select_checked = (
      sum([ent.is_selected for ent in list_entries]) == 1 or
      current_select_status == SELECT_ALL
    )

    if display_select_checked:
      click_count = 1 if select_status == SELECT_NONE else 2
    else:
      click_count = 1 if select_status == SELECT_ALL else 2

    head_line_element = self.page.locator(locators.LIST_HEADER).first
    multi_select_button_element = head_line_element.locator(locators.MULTI_SELECT_BUTTON).first

    for _ in range(click_count):
      await multi_select_button_element.click()
      await self.page.wait_for_timeout(500)

  async def select_files(self, file_names: list[str]):
    await self.multi_select_to(SELECT_NONE)
    for file_name in file_names:
      name_element = self.page.locator(locators.file_link(file_name)).first
      await name_element.wait_for(state="visible")
      dd_element = name_element.locator(locators.FILE_ITEM_XPATH)
      button_element = dd_element.locator(locators.ITEM_SELECT_CHECKBOX).first
      await button_element.click()
      await self.page.wait_for_timeout(200)

  @staticmethod
  def GetCurrentMultiSelectStatus(entries: list[BaiduPanEntry]) -> str:
    total_count = len(entries)
    selected_count = sum([ent.is_selected for ent in entries])

    if total_count == selected_count:
      return SELECT_ALL
    elif selected_count == 0:
      return SELECT_NONE
    else:
      return SELECT_PART
