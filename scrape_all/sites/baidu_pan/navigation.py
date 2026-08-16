import logging
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import Page, Locator
from typing import List, Optional
from scrape_all.sites.baidu_pan.predicates import WaitForBaidupanSharedLinkStable

SELECT_ALL = "all"
SELECT_PART = "part"
SELECT_NONE = "none"


async def IsInSharedLinkPage(page: Page) -> bool:
  """判断是否在分享页面"""
  title = await page.title()
  return "百度网盘" in title


class BaiduPanEntry:
  def __init__(self):
    self.name = None
    self.is_dir = False
    self.is_selected = False
  
  def __repr__(self):
    return f"BaiduPanEntry(name={self.name}, is_dir={self.is_dir}, is_selected={self.is_selected})"


class BaiduPanSharedLinkNavigation:
  @staticmethod
  async def GetCurrentSharedLinkPath(page: Page) -> str:
    if not await IsInSharedLinkPage(page):
      raise RuntimeError("not in shared link page")

    await WaitForBaidupanSharedLinkStable(page)
    
    path_holder_element = page.locator(".FuIxtL").first
    style_value = await path_holder_element.get_attribute("style")
    if style_value and "none" in style_value:
      return "/"   # root path
      
    full_path_element = page.locator("li[node-type='tbAudfb']").first
    path_text = await full_path_element.text_content()
    if path_text:
      path_text = path_text.replace(">", "/")
      return path_text.removeprefix("全部文件")
      
    return "/"

  @staticmethod
  async def ListCurrentSharedLinkFiles(page: Page) -> List[BaiduPanEntry]:
    """
    returns:
      [BaiduPanEntry, ...]
    """
    if not await IsInSharedLinkPage(page):
      raise RuntimeError("not in shared link page")

    await WaitForBaidupanSharedLinkStable(page)
    
    folder_content_element = page.locator(".vdAfKMb").first
    content_html = await folder_content_element.evaluate("el => el.outerHTML") 
    soup = BeautifulSoup(content_html, "lxml")

    all_dds = soup.find_all("dd")
    result = []
    for dd in all_dds:
      is_dir = False
      is_selected = "JS-item-active" in dd.attrs["class"]
      
      content_name = dd.find(class_="filename").attrs["title"]
      file_icon_soup = dd.find(class_="JS-fileicon")
      for attr in file_icon_soup.attrs["class"]:
        if "dir" in attr:
          is_dir = True
          break

      ent = BaiduPanEntry()
      ent.name = content_name
      ent.is_dir = is_dir
      ent.is_selected = is_selected
      result.append(ent)
    return result

  @staticmethod
  async def AccessFolder(page: Page, folder_name: str):
    folder_locator = page.locator(f"a.filename[title='{folder_name}']").first
    await folder_locator.wait_for(state="visible")
    await folder_locator.click()
    
    await WaitForBaidupanSharedLinkStable(page)
    await page.wait_for_timeout(500)

  @staticmethod
  async def ReturnToPrevFolder(page: Page) -> bool:
    try:
      return_locator = page.get_by_text("返回上一级").first
      await return_locator.wait_for(state="visible")
      await return_locator.click()
      
      await WaitForBaidupanSharedLinkStable(page)
      return True
    except Exception as e:
      logging.error(f"return to prev folder failed: {e}")
      return False

  @staticmethod
  async def MultiSelectTo(page: Page, select_status: str):
    """
    select_status: accept [all, none]
    """
    if select_status not in (SELECT_NONE, SELECT_ALL):
      raise RuntimeError("invalid select status")
      
    list_entries = await BaiduPanSharedLinkNavigation.ListCurrentSharedLinkFiles(page)
    current_select_status = BaiduPanSharedLinkNavigation.GetCurrentMultiSelectStatus(list_entries)
    
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
    
    head_line_element = page.locator("ul.QAfdwP.tvPMvPb").first
    multi_select_button_element = head_line_element.locator("span.zbyDdwb").first
    
    for _ in range(click_count):
      await multi_select_button_element.click()
      await page.wait_for_timeout(500)

  @staticmethod
  async def SelectFiles(page: Page, file_names: List[str]):
    await BaiduPanSharedLinkNavigation.MultiSelectTo(page, SELECT_NONE)
    for file_name in file_names:
      name_element = page.locator(f"a.filename[title='{file_name}']").first
      await name_element.wait_for(state="visible")
      dd_element = name_element.locator("xpath=./ancestor::dd[1]")
      button_element = dd_element.locator(".EOGexf").first
      await button_element.click()
      await page.wait_for_timeout(200)

  # @staticmethod
  # async def OpenSaveToDialog(page: Page):
  #   button_element = page.locator("div.bottom-save-path-icon").first
  #   await button_element.wait_for(state="visible")
  #   await button_element.click()
  #   await page.wait_for_timeout(200)
  #   await page.wait_for_load_state("load")

  """
  Simple judgement
  """
  @staticmethod
  def GetCurrentMultiSelectStatus(entries: List[BaiduPanEntry]) -> str:
    total_count = len(entries)
    selected_count = sum([ent.is_selected for ent in entries])
    
    if total_count == selected_count:
      return SELECT_ALL
    elif selected_count == 0:
      return SELECT_NONE
    else:
      return SELECT_PART