
import argparse, asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
import logging
logging.basicConfig(
  level=logging.NOTSET,
  format="[%(asctime)s] %(message)s",
)

from playwright.async_api import TimeoutError as PlaywrightTimeout

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.cangku import locators
from scrape_all.sites.cangku.login import CangkuLogin
from scrape_all.sites.cangku.post_filter import (
  is_target_post, meta_labels, parse_collection_boxes,
)
from scrape_all.sites.cangku.qr import decode_qr_bytes, fetch_image
from config import CANGKU_PROXY_SERVER

# 解析探针（只读，不写库）：对帖子页跑完整解析链——
#   1) 分类过滤：meta-label 含「动画」才工况内
#   2) 工况内：折叠卡标题含「合集」的 dl-box 解析 meta（提取码/解压密码），
#      dl-item 的二维码图下载解码出真实网盘链接
# 页面 DOM 存 data/samples/ 供离线分析。
#
# 用法：
#   python scripts/probe_cangku.py                    # 默认对比：219673（应工况内）/ 228707（应工况外）
#   python scripts/probe_cangku.py URL1 [URL2 ...]    # 指定帖子

DEFAULT_POSTS = [
    "https://cangku.moe/archives/219673",
    "https://cangku.moe/archives/228707",
]

SAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "samples")


def dump(name, html):
  path = os.path.join(SAMPLES_DIR, name)
  os.makedirs(SAMPLES_DIR, exist_ok=True)
  with open(path, "w", encoding="utf-8") as f:
    f.write(html)
  print(f"saved: {path} ({len(html)} chars)")


async def resolve_item_link(page, qr_image_url: str) -> str:
  """浏览器里取二维码并解码；失败返回 <...> 描述（探针要看得见错误）"""
  try:
    data = await fetch_image(page, qr_image_url)
    return decode_qr_bytes(data) or "<解码结果为空>"
  except Exception as e:
    return f"<取图/解码失败: {e}>"


async def report_parse(page, html):
  if not is_target_post(html):
    print("非目标分类（工况外），不解析")
    return
  boxes = parse_collection_boxes(html)
  print(f"collection boxes: {len(boxes)}")
  for box in boxes:
    print(f"\n[collapse] {box.card_title!r}  (box) {box.title!r}  date={box.date!r} from={box.source!r}")
    print(f"  info: {box.info!r}")
    print(f"  提取码={box.extract_pwd!r}  解压密码={box.unzip_pwd!r}")
    for item in box.items:
      if item.qr_image_url:
        print(f"  - {item.name!r}  qr={item.qr_image_url}")
        print(f"      -> {await resolve_item_link(page, item.qr_image_url)}")
      else:
        print(f"  - {item.name!r}  (无二维码地址，不是第一种情况)")


async def probe_post(page, url):
  post_id = url.rstrip("/").rsplit("/", 1)[-1]
  print(f"\n=== post page {url}")
  await page.goto(url)
  try:
    await page.wait_for_selector(locators.META_LABEL, timeout=15000)
  except PlaywrightTimeout:
    print(f"no meta-label rendered (page.url={page.url})")   # 留现场继续判定
  html = await page.content()
  dump(f"post_{post_id}.html", html)

  labels = meta_labels(html)
  print(f"meta-labels: {labels}")
  print(f"is_target: {is_target_post(html)}")
  await report_parse(page, html)


async def main():
  parser = argparse.ArgumentParser(description="cangku 解析探针（只读）")
  parser.add_argument("post_urls", nargs="*", help="要探测的帖子 URL；默认对比 219673/228707")
  args = parser.parse_args()
  urls = args.post_urls or DEFAULT_POSTS

  async with BrowserSession(CANGKU_PROXY_SERVER, stealth=True) as session:
    await CangkuLogin.GuaranteeCangkuLogin(session.context)

    page = await session.new_page()
    try:
      for url in urls:
        await probe_post(page, url)
    finally:
      await page.close()

  print("\ndone, samples saved in data/samples/")

asyncio.run(main())
