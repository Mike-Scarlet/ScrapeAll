
import argparse, asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
import logging
logging.basicConfig(
  level=logging.NOTSET,
  format="[%(asctime)s] %(message)s",
)

from bs4 import BeautifulSoup

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.cangku import locators
from scrape_all.sites.cangku.consts import CangkuDef
from scrape_all.sites.cangku.login import CangkuLogin
from config import CANGKU_PROXY_SERVER, YEJIANG_USER_ID

# 只读取样（步骤1）：把列表页和帖子的 DOM 存到 data/samples/ 供离线分析，
# 日志打印能解析出的字段。不写库、不点任何交互元素。
#
# 用法：
#   python scripts/probe_cangku.py                          # 列表第1页 + 第一张卡的帖子
#   python scripts/probe_cangku.py --page 3                 # 只看列表第3页（老帖时间格式）
#   python scripts/probe_cangku.py https://cangku.moe/archives/228710   # 只探测指定帖子

SAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "samples")


def dump(name, html):
  path = os.path.join(SAMPLES_DIR, name)
  os.makedirs(SAMPLES_DIR, exist_ok=True)
  with open(path, "w", encoding="utf-8") as f:
    f.write(html)
  print(f"saved: {path} ({len(html)} chars)")


def full_url(href):
  if href.startswith("http"):
    return href
  return f"{CangkuDef.cangku_root_url}{href}"


async def probe_list(page, page_no):
  url = f"{CangkuDef.cangku_root_url}/user/{YEJIANG_USER_ID}/post?page={page_no}"
  print(f"\n=== list page {url}")
  await page.goto(url)
  await page.wait_for_timeout(1500)   # 不 wait_for_selector：空页/翻过头时不崩

  container = await page.query_selector(locators.USER_POST_CONTAINER)
  if container is None:
    print(f"no #user-post container (page.url={page.url})")
    dump(f"list_p{page_no}_no_container.html", await page.content())
    return None
  html = await container.evaluate("el => el.outerHTML")
  dump(f"list_p{page_no}.html", html)

  soup = BeautifulSoup(html, "lxml")
  cards = soup.select(locators.POST_CARD)
  print(f"post cards: {len(cards)}  (page.url={page.url})")
  for i, card in enumerate(cards):
    a = card.find("a", href=True)
    t = card.find("time")
    dt_attr = t.get("datetime") if t else None
    shown = " ".join(t.get_text(strip=True).split()) if t else None
    print(f"  card {i:2d}: {a['href'] if a else None}  datetime={dt_attr!r}  shown={shown!r}")
  for i, card in enumerate(cards[:3]):
    text = " ".join(card.get_text(" ", strip=True).split())
    print(f"--- card {i} text: {text[:200]}")
  if cards and cards[0].find("a", href=True):
    return cards[0].find("a", href=True)["href"]
  return None


async def probe_post(page, href):
  url = full_url(href)
  post_id = url.rstrip("/").rsplit("/", 1)[-1]
  print(f"\n=== post page {url}")
  await page.goto(url)
  await page.wait_for_timeout(1500)   # 等渲染，选择器全部用 count/all 容错

  dump(f"post_{post_id}.html", await page.content())

  labels = []
  for el in await page.locator(locators.META_LABEL).all():
    labels.append((await el.text_content()).strip())
  print(f"labels: {labels}")

  cards = await page.locator(locators.COLLAPSE_CARD).all()
  print(f"collapse cards: {len(cards)}")
  for i, card in enumerate(cards):
    btns = card.locator(locators.COLLAPSE_BTN)
    title = (await btns.first.text_content()).strip() if await btns.count() else ""
    print(f"--- card {i} title: {title!r}")
    for j, dl_box in enumerate(await card.locator(locators.DL_BOX).all()):
      metas = {}
      for meta_el in await dl_box.locator(locators.DL_META_ITEM).all():
        key = await meta_el.locator("span").first.get_attribute("class")
        metas[key] = (await meta_el.text_content()).strip()
      print(f"    dl-box {j} meta: {metas}")
      for dl_el in await dl_box.locator(locators.DL_LINK_LIST).locator(locators.DL_ITEM).all():
        name = (await dl_el.text_content()).strip()
        onclick = await dl_el.get_attribute("onclick")
        print(f"      link {name!r} onclick={onclick!r}")


async def main():
  parser = argparse.ArgumentParser(description="cangku read-only probe")
  parser.add_argument("post_url", nargs="?", help="只探测这个帖子页（跳过列表）")
  parser.add_argument("--page", type=int, default=1, help="列表页码，默认 1")
  args = parser.parse_args()

  async with BrowserSession(CANGKU_PROXY_SERVER) as session:
    await CangkuLogin.GuaranteeCangkuLogin(session.context)

    page = await session.new_page()
    try:
      if args.post_url:
        await probe_post(page, args.post_url)
      else:
        first_href = await probe_list(page, args.page)
        if first_href and args.page == 1:
          await probe_post(page, first_href)
    finally:
      await page.close()

  print("\ndone, samples saved in data/samples/")

asyncio.run(main())
