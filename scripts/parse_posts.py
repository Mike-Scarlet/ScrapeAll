
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
import logging
logging.basicConfig(
  level=logging.NOTSET,
  format="[%(asctime)s] %(message)s",
)

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.cangku.pages.post_page import (
  load_post_html, post_id, save_qr_image,
)
from scrape_all.sites.cangku.post_filter import (
  baidu_qr_urls, extract_links, is_target_post, parse_collection_boxes,
)
from scrape_all.sites.cangku.qr import decode_qr_bytes, fetch_image
from scrape_all.sites.cangku.store import PostStore
from config import CANGKU_PROXY_SERVER

# parse 阶段入口：遍历待解析帖子（stat=1，新到旧），读本地 HTML——
#   非目标分类            -> stat=4（工况外终态）
#   合集 box + 二维码解码  -> stat=2（links_json 落库）
#   结构不符合当前规则（无合集卡 / box 无百度项 / 项无二维码 / 解码失败 /
#   内容非网盘）：保持 stat=1 并汇报原因，等规则补全后重跑（HTML 已在本地）。
# box 内只取名字带「百度」的下载项（219421：同盒还有 Pikpak 项，跳过）。
# 只有取二维码图要走浏览器（stealth，CF 挑战时等人工过验证）。

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cangku.db")


async def main():
  with PostStore(_DB_PATH) as store:
    posts = sorted(store.pending_parse(), key=lambda p: p.post_time, reverse=True)
    print(f"待解析帖子（stat=1）: {len(posts)}")
    if not posts:
      return

    stats = {"parsed": 0, "out_of_scope": 0, "anomaly": 0, "fail": 0}
    anomalies = []   # (url, [原因])；第一个就是需要人去看的

    async with BrowserSession(CANGKU_PROXY_SERVER, stealth=True) as session:
      page = await session.new_page()
      try:
        for i, post in enumerate(posts, 1):
          pid = post_id(post.url)
          try:
            html = load_post_html(pid)
          except FileNotFoundError:
            store.mark_parse_failed(post.url)
            stats["fail"] += 1
            print(f"[{i}/{len(posts)}] {pid} 本地 HTML 缺失 -> -2")
            continue

          if not is_target_post(html):
            store.mark_out_of_scope(post.url)
            stats["out_of_scope"] += 1
            print(f"[{i}/{len(posts)}] {pid} 工况外 -> 4")
            continue

          boxes = parse_collection_boxes(html)
          qr_urls = baidu_qr_urls(boxes)   # 只取「百度」项的二维码图，其余平台项不碰
          decoded = {}
          for j, qr_url in enumerate(qr_urls):
            try:
              data = await fetch_image(page, qr_url)
              save_qr_image(f"{pid}_{j}", data)
              decoded[qr_url] = decode_qr_bytes(data)
            except Exception as e:
              print(f"    qr 取图失败 {qr_url}: {e}")
              decoded[qr_url] = ""

          result = extract_links(boxes, lambda u: decoded.get(u, ""))
          if result.anomalies:
            stats["anomaly"] += 1
            anomalies.append((post.url, result.anomalies))
            print(f"[{i}/{len(posts)}] {pid} 不符合当前规则（保持待解析）")
            for reason in result.anomalies:
              print(f"    - {reason}")
          else:
            store.save_parsed(post.url, result.links)
            stats["parsed"] += 1
            print(f"[{i}/{len(posts)}] {pid} ok links={len(result.links)}")
      finally:
        await page.close()

    print(f"\n=== parse done: {stats}")
    if anomalies:
      url, reasons = anomalies[0]
      print(f"\n第一个不符合当前规则的帖子（请人工看下怎么处理）: {url}")
      for reason in reasons:
        print(f"  - {reason}")

asyncio.run(main())
