
from bs4 import BeautifulSoup

from scrape_all.sites.cangku import locators
from scrape_all.sites.cangku.consts import CangkuDef
from scrape_all.sites.cangku.history import PostRef, extract_time_text

# 纯逻辑模块：#user-post 容器 HTML -> PostRef 列表，不依赖 playwright（fixture 单测）


def parse_post_cards(container_html: str) -> list[PostRef]:
  """逐卡解析：url 取卡片主链接，时间优先 <time> 的 datetime 属性（秒级 UTC）

  时间来源优先级：datetime 属性 > time 显示文本 > 卡片整段文本尾部兜底。
  解析不出时间的卡 time_text=None（不丢帖子，由 plan_page 决定去留）。
  """
  soup = BeautifulSoup(container_html, "lxml")
  refs = []
  for card in soup.select(locators.POST_CARD):
    a = card.find("a", href=True)
    if not a:
      continue
    href = a["href"]
    url = href if href.startswith("http") else f"{CangkuDef.cangku_root_url}{href}"

    title = (a.get("title") or "").strip()
    if not title:
      title_div = card.select_one(locators.CARD_TITLE)
      title = title_div.get_text(strip=True) if title_div else ""

    t = card.find("time")
    if t is not None:
      time_text = t.get("datetime") or " ".join(t.get_text(" ", strip=True).split())
    else:
      time_text = extract_time_text(card.get_text(" ", strip=True))

    refs.append(PostRef(url=url, title=title, time_text=time_text))
  return refs
