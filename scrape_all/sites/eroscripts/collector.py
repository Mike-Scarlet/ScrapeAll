
import logging
from dataclasses import dataclass

from playwright.async_api import BrowserContext

from scrape_all.sites.eroscripts.api import ErosApi
from scrape_all.sites.eroscripts.history import parse_cutoff, plan_page, ref_time
from scrape_all.sites.eroscripts.list_parse import parse_topic_list
from scrape_all.sites.eroscripts.store import TopicStore, history_done_key, tag_slug_from_url

# collect 阶段编排：沿 bumped_at 从新到老翻 tag 列表到 cutoff / 已覆盖边界，
# 新帖与被顶起的更新帖落库（stat=DISCOVERED）。语义同 cangku collect，
# 停页与更新检测基于 (topic_id, bumped_at)。


@dataclass
class CollectResult:
  pages: int = 0
  new_topics: int = 0
  updated_topics: int = 0
  stop_reason: str = ""


class TagCollector:
  def __init__(self, context: BrowserContext, tag_url: str, store: TopicStore,
               cutoff_text: str, page_limit: int = 100):
    self.context = context
    self.tag_url = tag_url.rstrip("/")
    self.slug = tag_slug_from_url(self.tag_url)
    self.store = store
    self.cutoff = parse_cutoff(cutoff_text)
    if self.cutoff is None:
      raise ValueError(f"cutoff 无法解析: {cutoff_text!r}")
    self.page_limit = page_limit

  async def Run(self) -> CollectResult:
    result = CollectResult()

    # 回填未完成前不因已覆盖帖停页（topic_id+bumped_at 去重吸收对已见页的重走）；
    # 自然触底置 history_done 后，增量跑遇到已覆盖帖即停
    done = self.store.get_flag(history_done_key(self.slug))
    known = self.store.known_bumped()
    logging.info(
        f"collect start: tag={self.slug} cutoff={self.cutoff} "
        f"history_done={done} known_topics={len(known)}")

    api = ErosApi(self.context)
    try:
      for page_no in range(1, self.page_limit + 1):
        page_json = await api.get_tag_page(self.tag_url, page_no)
        refs = parse_topic_list(page_json)
        decision = plan_page(refs, cutoff=self.cutoff, known=known, stop_on_known=done)
        logging.info(
            f"page {page_no}: topics={len(refs)} new={len(decision.new_refs)} "
            f"updated={len(decision.updated_refs)} stop={decision.stop_reason or '-'}")

        if decision.new_refs or decision.updated_refs:
          n_new, n_upd = self.store.upsert_topics(decision.new_refs, decision.updated_refs)
          result.new_topics += n_new
          result.updated_topics += n_upd
          for r in decision.new_refs + decision.updated_refs:
            known[r.topic_id] = ref_time(r)

        result.pages = page_no
        if not decision.should_continue:
          result.stop_reason = decision.stop_reason
          break
      else:
        result.stop_reason = "page_limit"
        logging.warning(f"reached page_limit={self.page_limit}，未自然停止，请检查")

      if result.stop_reason in ("reached_cutoff", "empty_page"):
        self.store.set_flag(history_done_key(self.slug))
    finally:
      await api.close()

    logging.info(
        f"collect done: tag={self.slug} pages={result.pages} "
        f"new_topics={result.new_topics} updated_topics={result.updated_topics} "
        f"stop={result.stop_reason}")
    return result
