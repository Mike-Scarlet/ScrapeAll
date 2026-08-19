
import argparse, asyncio, logging, os, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
logging.basicConfig(
  level=logging.NOTSET if os.environ.get("EROS_DEBUG") else logging.INFO,
  format="[%(asctime)s] %(message)s",
)

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.eroscripts.collector import TagCollector
from scrape_all.sites.eroscripts.fetcher import TopicFetcher
from scrape_all.sites.eroscripts.login import ErosLogin
from scrape_all.sites.eroscripts.store import (
    Stat, TopicStore, history_done_key, tag_slug_from_url,
)
from scrape_all.sites.eroscripts.topic_files import load_topic_json
from scrape_all.sites.eroscripts.topic_parse import (
    host_of, links_to_json, parse_topic_links,
)
from config import (
    EROS_CATEGORY_ID, EROS_HISTORY_CUTOFF, EROS_PAGE_LIMIT,
    EROS_PROXY_SERVER, EROS_TAG_URL,
)

# 阶段入口：
#   python scripts/scrape_eroscripts.py                  # 全流程 collect->fetch->parse
#   python scripts/scrape_eroscripts.py --stage fetch    # 只跑某阶段（collect/fetch/parse）
#   python scripts/scrape_eroscripts.py --stage parse --retry-deferred
#   python scripts/scrape_eroscripts.py --full-history   # 全量回填（忽略 cutoff 翻到 tag 底）
#
#   collect  登录 -> 沿 bumped_at 翻 tag 列表到 cutoff / 已覆盖边界 -> 新帖落库（stat=0）
#   fetch    工况过滤（category!=14 -> stat=4，不发请求）-> topic 页 JSON 落盘 -> stat=1
#   parse    纯离线读盘：category 复核 -> 全帖链接提取分类落 links_json -> stat=2；
#           一条 script/media 都没解析出来的挂起 stat=5（--retry-deferred 连着重跑），
#           域名表等规则升级后 --reparse 离线重分类全部已解析帖，不用重新抓页

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "eroscripts.db")


async def run_browser_stages(store: TopicStore, stage: str, full_history: bool):
  """collect / fetch 都要浏览器登录态，共用一个 session"""
  async with BrowserSession(EROS_PROXY_SERVER) as session:
    await ErosLogin.GuaranteeErosLogin(session.context)

    if stage in ("all", "collect"):
      if full_history:
        # 全量回填：清掉 history_done（否则第 1 页全是已覆盖帖直接停），
        # cutoff 置空翻到 tag 底；topic_id 去重吸收缓存页重叠，安全重跑
        store.clear_flag(history_done_key(tag_slug_from_url(EROS_TAG_URL)))
        print("full-history: history_done 已清，忽略 cutoff 翻到 tag 底")
      collector = TagCollector(
          session.context, EROS_TAG_URL, store,
          None if full_history else EROS_HISTORY_CUTOFF, EROS_PAGE_LIMIT)
      result = await collector.Run()
      print(f"\n=== collect done: pages={result.pages} "
            f"new={result.new_topics} updated={result.updated_topics} "
            f"stop={result.stop_reason}")

    if stage in ("all", "fetch"):
      result = await TopicFetcher(session.context, store, EROS_CATEGORY_ID).Run()
      print(f"\n=== fetch done: fetched={result.fetched} "
            f"out_of_scope={result.out_of_scope} failed={result.failed}")


def run_parse(store: TopicStore, retry_deferred: bool, reparse: bool):
  topics = sorted(store.pending_parse(include_deferred=retry_deferred or reparse,
                                      include_parsed=reparse),
                  key=lambda t: t.bumped_at or "", reverse=True)
  print(f"待解析 topic（{'含挂起/已解析重跑' if reparse else '含挂起重试' if retry_deferred else 'stat=1'}）: {len(topics)}")

  stats = Counter()
  topic_kinds = Counter()   # 有该 kind 链接的 topic 数
  link_kinds = Counter()    # 该 kind 链接总数
  other_hosts = Counter()   # other 的域名分布，用来补域名表
  deferred_topics = []

  for i, t in enumerate(topics, 1):
    try:
      j = load_topic_json(t.topic_id)
    except FileNotFoundError:
      store.mark_parse_failed(t.topic_id)
      stats["failed"] += 1
      print(f"[{i}/{len(topics)}] {t.topic_id} 本地 JSON 缺失 -> -2")
      continue

    if j.get("category_id") != EROS_CATEGORY_ID:
      store.mark_out_of_scope(t.topic_id)
      stats["out_of_scope"] += 1
      continue

    links = parse_topic_links(j)
    kinds = {l.kind for l in links}
    if not ({"script", "media"} & kinds):
      # Scripts 分类的帖一条脚本/媒体链接都没有：结构超出预期，挂起人工看
      store.mark_deferred(t.topic_id)
      stats["deferred"] += 1
      deferred_topics.append(t)
      print(f"[{i}/{len(topics)}] {t.topic_id} 无 script/media 链接，挂起 -> 5 "
            f"kinds={sorted(kinds) or '无链接'} {t.url}")
      continue

    store.save_parsed(t.topic_id, links_to_json(links))
    stats["parsed"] += 1
    for k in kinds:
      topic_kinds[k] += 1
    for l in links:
      link_kinds[l.kind] += 1
      if l.kind == "other":
        other_hosts[host_of(l.url)] += 1
    if i % 50 == 0 or i == len(topics):
      print(f"parse progress {i}/{len(topics)}")

  print(f"\n=== parse done: {dict(stats)}")
  print(f"topic 覆盖（有该类链接的 topic 数）: {dict(topic_kinds)}")
  print(f"链接总数按 kind: {dict(link_kinds)}")
  if other_hosts:
    print(f"other 链接域名 Top15（补表参考）: {other_hosts.most_common(15)}")
  if deferred_topics:
    print(f"挂起 topic {len(deferred_topics)} 个，前 3 个请人工过目:")
    for t in deferred_topics[:3]:
      print(f"  - {t.url} 「{t.title}」")


async def main():
  ap = argparse.ArgumentParser(description="eroscripts 抓取（collect/fetch/parse）")
  ap.add_argument("--stage", choices=("all", "collect", "fetch", "parse"),
                  default="all", help="跑哪个阶段（默认全流程）")
  ap.add_argument("--retry-deferred", action="store_true",
                  help="parse 阶段连同挂起 topic（stat=5）一起重跑")
  ap.add_argument("--reparse", action="store_true",
                  help="parse 阶段连同已解析 topic（stat=2/5）一起重跑：域名表等"
                       "规则升级后离线重分类，不用重新抓页")
  ap.add_argument("--full-history", action="store_true",
                  help="collect 全量回填：清 history_done、忽略 EROS_HISTORY_CUTOFF "
                       "翻到 tag 底（topic_id 去重保证可安全重跑）")
  args = ap.parse_args()

  used_browser = args.stage in ("all", "collect", "fetch")
  with TopicStore(_DB_PATH) as store:
    if used_browser:
      await run_browser_stages(store, args.stage, full_history=args.full_history)
    if args.stage in ("all", "parse"):
      run_parse(store, retry_deferred=args.retry_deferred, reparse=args.reparse)
    print(f"\nstat 分布: {store.stat_counts()}")

  if used_browser:
    try:
      input("\npress enter to exit ")
    except EOFError:
      pass


asyncio.run(main())
