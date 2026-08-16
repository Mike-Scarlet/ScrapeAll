
from typing import Optional

from scrape_all.sites.baidu_pan.pages.shared_link_page import SharedLinkPage
from scrape_all.sites.baidu_pan.tree import EntryInfo, PanNode, StopPolicy, walk_tree


class ShareWalker:
  """把 SharedLinkPage 桥接为 walk_tree 的 lister：goto_path 跳转 + list_files 列目录"""
  def __init__(self, page: SharedLinkPage):
    self.page = page

  async def walk(self, policy: Optional[StopPolicy] = None) -> PanNode:
    async def lister(path: str) -> list[EntryInfo]:
      await self.page.goto_path(path)
      entries = await self.page.list_files()
      return [EntryInfo(e.name, e.is_dir, e.size_text, e.mtime_text) for e in entries]

    return await walk_tree(lister, policy)
