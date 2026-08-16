
import argparse, asyncio, os, sys

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
from config import CANGKU_FORCE_IDS, CANGKU_PROXY_SERVER

# parse 阶段入口：遍历待解析帖子（stat=1，新到旧），读本地 HTML——
#   分类严格：meta-label 无「动画」（含没挂标签的）-> stat=4（工况外终态）；
#     例外帖子走 config.CANGKU_FORCE_IDS 后门，按 id 跳过分类检查
#   合集 box + 二维码解码  -> stat=2（links_json 落库）
#   结构不符合当前规则（无合集卡 / box 无百度项 / 项无二维码 / 解码失败 /
#   内容非网盘）：
#     取图全部成功的 -> 确定性超规，stat=5 挂起（非失败），等规则补全后
#       python parse_posts.py --retry-deferred 重跑收编；
#     取图有失败的   -> 可能是暂时性网络问题，保持原状态（1/5）下轮再试。
# box 内只取名字带「百度」的下载项（219421：同盒还有 Pikpak 项，跳过）。
# 只有取二维码图要走浏览器（stealth，CF 挑战时等人工过验证）。

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cangku.db")


async def main(retry_deferred: bool = False):
  with PostStore(_DB_PATH) as store:
    posts = sorted(store.pending_parse(include_deferred=retry_deferred),
                   key=lambda p: p.post_time, reverse=True)
    print(f"待解析帖子（stat=1{'/5' if retry_deferred else ''}）: {len(posts)}")
    if not posts:
      return

    stats = {"parsed": 0, "out_of_scope": 0, "deferred": 0, "pending": 0, "fail": 0}
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

          if pid in CANGKU_FORCE_IDS:
            # id 后门（config.CANGKU_FORCE_IDS）：跳过严格分类检查，直接结构解析
            print(f"[{i}/{len(posts)}] {pid} 后门命中（CANGKU_FORCE_IDS），跳过分类过滤")
          elif not is_target_post(html):
            store.mark_out_of_scope(post.url)
            stats["out_of_scope"] += 1
            print(f"[{i}/{len(posts)}] {pid} 工况外 -> 4")
            continue

          boxes = parse_collection_boxes(html)
          qr_urls = baidu_qr_urls(boxes)   # 只取「百度」项的二维码图，其余平台项不碰
          decoded = {}
          fetch_failed = False
          for j, qr_url in enumerate(qr_urls):
            try:
              data = await fetch_image(page, qr_url)
              save_qr_image(f"{pid}_{j}", data)
              decoded[qr_url] = decode_qr_bytes(data)
            except Exception as e:
              print(f"    qr 取图失败 {qr_url}: {e}")
              decoded[qr_url] = ""
              fetch_failed = True

          result = extract_links(boxes, lambda u: decoded.get(u, ""))
          if result.anomalies:
            anomalies.append((post.url, result.anomalies))
            if fetch_failed:
              stats["pending"] += 1
              print(f"[{i}/{len(posts)}] {pid} 不符合当前规则且取图有失败（状态保持）")
            else:
              store.mark_deferred(post.url)
              stats["deferred"] += 1
              print(f"[{i}/{len(posts)}] {pid} 结构超出当前规则，挂起 -> 5")
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
      print(f"\n第一个挂起/待重试帖子的原因（请人工看下怎么处理）: {url}")
      for reason in reasons:
        print(f"  - {reason}")


if __name__ == "__main__":
  ap = argparse.ArgumentParser(description="cangku parse 阶段")
  ap.add_argument("--retry-deferred", action="store_true",
                  help="连同挂起帖（stat=5，结构超规）一起重跑")
  asyncio.run(main(retry_deferred=ap.parse_args().retry_deferred))
