
import time

from playwright.async_api import Page

from scrape_all.sites.cangku import locators
from scrape_all.sites.cangku.consts import CangkuDef
from scrape_all.sites.cangku.history import PostRef
from scrape_all.sites.cangku.list_parse import parse_post_cards

CARD_FILL_TIMEOUT = 10    # 卡片填充轮询上限（秒）；空页会等满此时长
FULL_PAGE_CARDS = 12      # 站点分页大小，满页可提前结束等待


class PostListPage:
  def __init__(self, page: Page):
    self.page = page

  async def get_posts(self, user_id: str, page_no: int) -> list[PostRef]:
    """取一页帖子卡片。卡片由前端异步填充（容器先渲染、内容后到）：
    容器出现后轮询等卡片数量稳定再取 outerHTML。
    空页（翻过界）容器一直在但卡片始终为 0，轮询到超时返回 []。
    """
    url = f"{CangkuDef.cangku_root_url}/user/{user_id}/post?page={page_no}"
    await self.page.goto(url)
    await self.page.wait_for_selector(locators.USER_POST_CONTAINER, timeout=15000)

    card_sel = f"{locators.USER_POST_CONTAINER} {locators.POST_CARD}"
    deadline = time.monotonic() + CARD_FILL_TIMEOUT
    last_count = -1
    stable_since = None
    while time.monotonic() < deadline:
      now = time.monotonic()
      n = await self.page.locator(card_sel).count()
      if n != last_count:
        last_count, stable_since = n, now
      if n > 0 and stable_since is not None:
        held = now - stable_since
        if (n >= FULL_PAGE_CARDS and held >= 0.5) or held >= 1.2:
          break
      await self.page.wait_for_timeout(200)

    container = await self.page.query_selector(locators.USER_POST_CONTAINER)
    html = await container.evaluate("el => el.outerHTML")
    return parse_post_cards(html)
