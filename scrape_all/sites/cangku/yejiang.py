
import logging
from dataclasses import dataclass

from playwright.async_api import BrowserContext

from scrape_all.sites.cangku.history import now_utc, parse_time, plan_page, ref_time
from scrape_all.sites.cangku.pages.post_list_page import PostListPage
from scrape_all.sites.cangku.store import PostStore, history_done_key

# collect 阶段编排：翻列表页到 cutoff / 已覆盖边界，新帖与更新帖落库（stat=DISCOVERED）。
# 停页与更新检测都基于 (url, 时间戳)：库内已有但时间戳变新 = 帖子被作者更新过，重置重走。


@dataclass
class CollectResult:
  pages: int = 0
  new_posts: int = 0
  updated_posts: int = 0
  stop_reason: str = ""


class YejiangCollector:
  def __init__(self, context: BrowserContext, user_id: str, store: PostStore,
               cutoff_text: str, page_limit: int = 100):
    self.context = context
    self.user_id = user_id
    self.store = store
    self.cutoff = parse_time(cutoff_text)
    if self.cutoff is None:
      raise ValueError(f"cutoff 无法解析: {cutoff_text!r}")
    self.page_limit = page_limit

  async def Run(self) -> CollectResult:
    result = CollectResult()

    # 回填未完成前不因已覆盖帖停页（url+时间戳去重吸收对已见页的重走）；
    # 自然触底置 history_done 后，增量跑遇到已覆盖帖即停
    done = self.store.get_flag(history_done_key(self.user_id))
    known = self.store.known_times()
    logging.info(
        f"collect start: user={self.user_id} cutoff={self.cutoff} "
        f"history_done={done} known_posts={len(known)}")

    page = await self.context.new_page()
    list_page = PostListPage(page)
    try:
      for page_no in range(1, self.page_limit + 1):
        now = now_utc()
        refs = await list_page.get_posts(self.user_id, page_no)
        decision = plan_page(refs, cutoff=self.cutoff, known=known, now=now,
                             stop_on_known=done)
        logging.info(
            f"page {page_no}: cards={len(refs)} new={len(decision.new_refs)} "
            f"updated={len(decision.updated_refs)} stop={decision.stop_reason or '-'}")

        if decision.new_refs or decision.updated_refs:
          n_new, n_upd = self.store.upsert_posts(
              decision.new_refs, decision.updated_refs, now_dt=now)
          result.new_posts += n_new
          result.updated_posts += n_upd
          for r in decision.new_refs + decision.updated_refs:
            known[r.url] = ref_time(r, now)

        result.pages = page_no
        if not decision.should_continue:
          result.stop_reason = decision.stop_reason
          break
      else:
        result.stop_reason = "page_limit"
        logging.warning(f"reached page_limit={self.page_limit}，未自然停止，请检查")

      if result.stop_reason in ("reached_cutoff", "empty_page"):
        self.store.set_flag(history_done_key(self.user_id))
    finally:
      await page.close()

    logging.info(
        f"collect done: pages={result.pages} new_posts={result.new_posts} "
        f"updated_posts={result.updated_posts} stop={result.stop_reason}")
    return result
