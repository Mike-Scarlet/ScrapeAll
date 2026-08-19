
import logging
from dataclasses import dataclass

from playwright.async_api import BrowserContext

from scrape_all.sites.eroscripts.api import ErosApi
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.sites.eroscripts.topic_files import save_topic_json

# fetch 阶段编排：工况过滤（列表 meta 里 category 不符的直接 OUT_OF_SCOPE，
# 不发请求）-> 逐 topic 拉 /t/<id>.json 落盘 -> FETCHED。
# payload 含 OP + 前 20 楼（discourse chunk_size）：脚本/下载链接基本都在 OP，
# 作者的脚本更新也几乎都在前 20 楼内，超长楼的尾巴不追。
# 新的优先抓（bumped_at 降序），中途断了重跑即续（stat 队列天然续传）。


@dataclass
class FetchResult:
  fetched: int = 0
  out_of_scope: int = 0
  failed: int = 0


class TopicFetcher:
  def __init__(self, context: BrowserContext, store: TopicStore, category_id: int):
    self.context = context
    self.store = store
    self.category_id = category_id

  async def Run(self) -> FetchResult:
    result = FetchResult()
    pending = sorted(self.store.pending_fetch(),
                     key=lambda t: t.bumped_at or "", reverse=True)
    out_ids = [t.topic_id for t in pending if t.category_id != self.category_id]
    todo = [t for t in pending if t.category_id == self.category_id]
    if out_ids:
      self.store.mark_out_of_scope_batch(out_ids)
    result.out_of_scope = len(out_ids)
    logging.info(f"fetch start: pending={len(pending)} "
                 f"out_of_scope={len(out_ids)} todo={len(todo)}")
    if not todo:
      return result

    api = ErosApi(self.context)
    try:
      for i, t in enumerate(todo, 1):
        try:
          j = await api.get_topic(t.topic_id)
        except RuntimeError as e:
          self.store.mark_fetch_failed(t.topic_id)
          result.failed += 1
          logging.warning(f"[{i}/{len(todo)}] topic {t.topic_id} 抓取失败 -> -1: {e}")
          continue
        save_topic_json(t.topic_id, j)   # 工况外也落盘，parse 阶段可复核
        # 以 topic 页为准复核工况（列表缓存里的 category 可能滞后）
        if j.get("category_id") != self.category_id:
          self.store.mark_out_of_scope(t.topic_id)
          result.out_of_scope += 1
        else:
          self.store.mark_fetched(t.topic_id)
          result.fetched += 1
        if i % 25 == 0 or i == len(todo):
          logging.info(f"fetch progress {i}/{len(todo)}")
    finally:
      await api.close()

    logging.info(f"fetch done: fetched={result.fetched} "
                 f"out_of_scope={result.out_of_scope} failed={result.failed}")
    return result
