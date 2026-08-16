
import asyncio
import logging
import re
from typing import Optional
from urllib.parse import quote, unquote
from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from scrape_all.sites.baidu_pan import locators
from scrape_all.sites.baidu_pan.errors import BaiduPanError
from scrape_all.sites.baidu_pan.predicates import WaitForBaidupanSharedLinkStable

SELECT_ALL = "all"
SELECT_PART = "part"
SELECT_NONE = "none"

# hash 路由里的内部路径前缀，如 "/sharelink1099915704074-927179428565472"
SHARELINK_PREFIX_RE = re.compile(r"(/sharelink[^/]+)")


def extract_share_prefix(url: str) -> Optional[str]:
  # hash 路径是百分号编码的（%2Fsharelink...），先解码再匹配
  m = SHARELINK_PREFIX_RE.search(unquote(url or ""))
  return m.group(1) if m else None


def parent_of(path: str) -> str:
  """'/A/B' -> '/A'；'/A' -> '/'；根 -> '/'"""
  path = path.rstrip("/")
  if not path or path == "/":
    return "/"
  cut = path.rfind("/")
  return path[:cut] if cut > 0 else "/"


def build_hash_url(base_url: str, internal_path: str, internal_parent: str) -> str:
  """构造任意层级的深链：base#list/path=<enc>&parentPath=<enc>（分隔符也要编码，与页面一致）"""
  return f"{base_url}#list/path={quote(internal_path, safe='')}&parentPath={quote(internal_parent, safe='')}"


def current_hash_path(page_url: str) -> Optional[str]:
  """从页面 URL 里解出当前所在的内部路径（hash 的 list/path 参数，解码后）"""
  if not page_url or "#list/path=" not in page_url:
    return None
  hash_part = page_url.split("#", 1)[1]
  path_value = hash_part.split("list/path=", 1)[1].split("&", 1)[0]
  return unquote(path_value)


def hash_path_matches(page_url: str, path: str) -> bool:
  """页面当前是否已停在分享内的 path（比较 URL hash，剥掉 sharelink 前缀）

  不能用面包屑做这个判断：深度 >= 2 只显示最后一级，
  停在 /Mimu/2025 时面包屑读出 "/2025"，goto_path("/2025") 会提前返回列错目录
  """
  current = current_hash_path(page_url)
  if current is None:
    return path == "/"          # 没有 hash = 刚打开的分享页，停在根
  prefix = extract_share_prefix(current)
  rel = current[len(prefix):] if prefix else current
  return rel == path


class BaiduPanEntry:
  def __init__(self):
    self.name = None
    self.is_dir = False
    self.is_selected = False
    self.size_text = None    # 页面原文，如 "326.1M"；文件夹为 "-"
    self.mtime_text = None   # 页面原文，如 "2025-10-04 02:55"

  def __repr__(self):
    return f"BaiduPanEntry(name={self.name}, is_dir={self.is_dir}, is_selected={self.is_selected})"

class SharedLinkPage:
  def __init__(self, page: Page, base_url: str = None):
    self.page = page
    self._base_url = base_url                # 去掉 hash 的分享链接，goto_path 依赖它
    self._share_prefix = None                # "/sharelink<id>"，首次跳子目录时发现

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
      # share/init?surl= 之类的链接加载后会被规范化成 /s/xxx 形式，
      # base 必须取加载后的真实 URL，否则每次 hash 跳转都变成整页重定向
      return SharedLinkPage(page, page.url.split("#")[0])

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

      size_soup = dd.find(class_=locators.FILE_SIZE_CLASS)
      mtime_soup = dd.find(class_=locators.FILE_MTIME_CLASS)

      ent = BaiduPanEntry()
      ent.name = content_name
      ent.is_dir = is_dir
      ent.is_selected = is_selected
      ent.size_text = size_soup.get_text(strip=True) if size_soup else None
      ent.mtime_text = mtime_soup.get_text(strip=True) if mtime_soup else None
      result.append(ent)

    names = [ent.name for ent in result]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
      # 同级同名会让按名字点击/勾选命中错误目标，提前暴露
      raise BaiduPanError(f"duplicate names in current folder: {sorted(duplicates)}")
    return result

  async def goto_path(self, path: str):
    """跳转到分享内任意目录（hash 深链，root 为 "/"）

    需要 base_url（通过 SharedLinkPage.open 打开才有）
    """
    if self._base_url is None:
      raise BaiduPanError("goto_path needs base_url, open page via SharedLinkPage.open")

    path = "/" + path.strip("/") if path.strip("/") else "/"
    if hash_path_matches(self.page.url, path):
      return

    if path == "/":
      internal = internal_parent = "/"
    else:
      prefix = await self._ensure_share_prefix()
      internal = prefix + path
      internal_parent = prefix + parent_of(path)

    await self._goto_hash(internal, internal_parent)

  async def _goto_hash(self, internal: str, internal_parent: str):
    """hash 跳转并等待列表就绪

    就绪信号是 /share/list 请求的 dir 参数等于目标路径（响应即证明目录正确，
    面包屑不可靠：深层只显示最后一级，长名还会截断）
    """
    url = build_hash_url(self._base_url, internal, internal_parent)
    if current_hash_path(self.page.url) == internal:
      return

    dir_param = "dir=" + quote(internal, safe="")
    try:
      async with self.page.expect_response(
          lambda r: "/share/list" in r.url and dir_param in r.url,
          timeout=10_000,
      ):
        await self.page.goto(url)
    except PlaywrightTimeoutError:
      logging.warning(f"no share/list response for {internal}, fall back to stable wait")

    await WaitForBaidupanSharedLinkStable(self.page)
    await self.page.wait_for_timeout(300)

  async def _ensure_share_prefix(self) -> str:
    if self._share_prefix:
      return self._share_prefix

    prefix = extract_share_prefix(self.page.url)
    if prefix is None:
      # 根目录的 hash 里没有前缀：进第一个子文件夹读一次再回根
      entries = await self.list_files()
      first_dir = next((e for e in entries if e.is_dir), None)
      if first_dir is None:
        raise BaiduPanError("no subfolder at root, cannot discover sharelink prefix")

      await self.access_folder(first_dir.name)
      prefix = extract_share_prefix(self.page.url)

    if prefix is None:
      raise BaiduPanError("cannot discover sharelink prefix from url")

    self._share_prefix = prefix
    return prefix

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
