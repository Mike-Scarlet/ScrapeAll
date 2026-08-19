
import json
import time
from datetime import datetime
from enum import IntEnum
from typing import Optional, Sequence

from python_general_lib.database.sqlite3_wrap.multiple_models_sqlite_database import \
    MultipleModelsSQLiteDatabase

from scrape_all.sites.eroscripts.history import TopicRef, parse_iso, to_iso
from scrape_all.storage.models import EroTopicItem, ScrapeMeta


class Stat(IntEnum):
  """topic 处理状态机；topic 被顶起（bumped_at 变新）时重置回 DISCOVERED 重走全程"""
  DISCOVERED = 0    # 刚被 walk 出来，仅有列表 meta
  FETCHED = 1       # topic 页已抓取保存
  PARSED = 2        # 已解析（工况内，links 已写入）
  CONSUMED = 3      # 解析结果已交后续流程处理（终态）
  OUT_OF_SCOPE = 4  # 解析过滤判定工况外（终态）
  DEFERRED = 5      # 结构超规挂起，规则补全后 --retry-deferred 重跑收编
  FETCH_FAILED = -1
  PARSE_FAILED = -2


def tag_slug_from_url(tag_url: str) -> str:
  """/tag/loli/68 -> loli（剥掉尾部的 tag id 后缀）"""
  parts = tag_url.rstrip("/").split("/")
  return parts[-2] if len(parts) >= 2 else tag_url


def history_done_key(tag_slug: str) -> str:
  """历史回填完成标志：只有自然触底（reached_cutoff/empty_page）才置位。
  置位前已覆盖帖不触发停页（中断重跑要把更深的页抓完），置位后增量跑
  遇到 (topic_id+bumped_at) 都已记录的帖子即停。"""
  return f"eros:tag:{tag_slug}:history_done"


class TopicStore:
  """eroscripts 抓取状态落库：topic 去重（topic_id 主键 + bumped_at 比对）、
  stat 流转、回填标志。独立 db 文件，不与 cangku 混。"""

  def __init__(self, db_path: str):
    self.db = MultipleModelsSQLiteDatabase(db_path, [EroTopicItem, ScrapeMeta])
    self.db.Initiate()

  def __enter__(self) -> "TopicStore":
    return self

  def __exit__(self, exc_type, exc, tb):
    self.close()

  def known_bumped(self) -> dict[int, Optional[datetime]]:
    """库内 topic_id -> 已记录 bumped_at（归一化过，可直接比较；解析失败为 None）"""
    rows = self.db.RawSelectFieldFromTableWithReturnFieldName(
        EroTopicItem, ["topic_id", "bumped_at"])
    return {row["topic_id"]: parse_iso(row["bumped_at"]) for row in rows}

  def upsert_topics(self, new_refs: Sequence[TopicRef],
                    updated_refs: Sequence[TopicRef] = (),
                    now: Optional[float] = None) -> tuple[int, int]:
    """collect 阶段写入。新帖插入（stat=DISCOVERED）；更新帖（被顶起）刷新 meta
    并重置回 DISCOVERED、清空 links（重新走一遍后续流程）。
    已覆盖帖（topic_id+bumped_at 都没变）由 plan_page 过滤，不会进到这里。
    返回 (新帖数, 更新帖数)。"""
    if now is None:
      now = time.time()
    known = self.known_bumped()

    def norm_created(ref: TopicRef) -> str:
      t = parse_iso(ref.created_at)
      return to_iso(t) if t else (ref.created_at or "")

    def norm_bumped(ref: TopicRef) -> str:
      t = parse_iso(ref.bumped_at)
      return to_iso(t) if t else (ref.bumped_at or "")

    new_items = []
    for ref in new_refs:
      if ref.topic_id in known:
        continue
      new_items.append(EroTopicItem(
          topic_id=ref.topic_id, url=ref.url, title=ref.title, author=ref.author,
          created_at=norm_created(ref), bumped_at=norm_bumped(ref),
          tags_json=json.dumps(list(ref.tags), ensure_ascii=False),
          category_id=ref.category_id, posts_count=ref.posts_count, views=ref.views,
          stat=int(Stat.DISCOVERED), links_json="", first_seen=now, last_seen=now))
      known[ref.topic_id] = parse_iso(ref.bumped_at)
    if new_items:
      self.db.InsertBatch(new_items, on_conflict="OR IGNORE")

    for ref in updated_refs:
      item = EroTopicItem(topic_id=ref.topic_id)
      item.url = ref.url
      item.title = ref.title
      item.author = ref.author
      item.created_at = norm_created(ref)
      item.bumped_at = norm_bumped(ref)
      item.tags_json = json.dumps(list(ref.tags), ensure_ascii=False)
      item.category_id = ref.category_id
      item.posts_count = ref.posts_count
      item.views = ref.views
      item.stat = int(Stat.DISCOVERED)
      item.links_json = ""
      item.last_seen = now
      self.db.RecordFieldChanged(
          item, ["url", "title", "author", "created_at", "bumped_at", "tags_json",
                 "category_id", "posts_count", "views", "stat", "links_json", "last_seen"])
    self.db.Commit()
    return len(new_items), len(updated_refs)

  # ---- 后续 fetch / parse 阶段的取队与状态流转（首版只用到 collect，先备好） ----

  def pending_fetch(self) -> list[EroTopicItem]:
    """待抓取 topic 页的帖子（DISCOVERED）"""
    return self.db.QueryRecords(EroTopicItem, where="stat = ?", params=(int(Stat.DISCOVERED),))

  def mark_fetched(self, topic_id: int):
    item = EroTopicItem(topic_id=topic_id, stat=int(Stat.FETCHED))
    self.db.RecordFieldChanged(item, ["stat"])
    self.db.Commit()

  def mark_fetch_failed(self, topic_id: int):
    item = EroTopicItem(topic_id=topic_id, stat=int(Stat.FETCH_FAILED))
    self.db.RecordFieldChanged(item, ["stat"])
    self.db.Commit()

  def pending_parse(self, include_deferred: bool = False) -> list[EroTopicItem]:
    stats = [int(Stat.FETCHED)] + ([int(Stat.DEFERRED)] if include_deferred else [])
    marks = ",".join("?" for _ in stats)
    return self.db.QueryRecords(EroTopicItem, where=f"stat in ({marks})", params=tuple(stats))

  def save_parsed(self, topic_id: int, links: list, stat: int = int(Stat.PARSED)):
    item = EroTopicItem(topic_id=topic_id)
    item.links_json = json.dumps(links, ensure_ascii=False)
    item.stat = stat
    self.db.RecordFieldChanged(item, ["links_json", "stat"])
    self.db.Commit()

  def mark_parse_failed(self, topic_id: int):
    item = EroTopicItem(topic_id=topic_id, stat=int(Stat.PARSE_FAILED))
    self.db.RecordFieldChanged(item, ["stat"])
    self.db.Commit()

  def mark_deferred(self, topic_id: int):
    item = EroTopicItem(topic_id=topic_id, stat=int(Stat.DEFERRED))
    self.db.RecordFieldChanged(item, ["stat"])
    self.db.Commit()

  def mark_out_of_scope(self, topic_id: int):
    item = EroTopicItem(topic_id=topic_id, stat=int(Stat.OUT_OF_SCOPE))
    self.db.RecordFieldChanged(item, ["stat"])
    self.db.Commit()

  def mark_consumed(self, topic_id: int):
    item = EroTopicItem(topic_id=topic_id, stat=int(Stat.CONSUMED))
    self.db.RecordFieldChanged(item, ["stat"])
    self.db.Commit()

  # ---- 元信息 ----

  def get_flag(self, key: str) -> bool:
    row = self.db.QueryOne(ScrapeMeta, where="key = ?", params=(key,))
    return row is not None and row.value == "1"

  def set_flag(self, key: str):
    self.db.InsertRecord(ScrapeMeta(key=key, value="1"), on_conflict="OR REPLACE")
    self.db.Commit()

  def clear_flag(self, key: str):
    self.db.RemoveRecord(ScrapeMeta(key=key, value=""))
    self.db.Commit()

  def close(self):
    self.db.Close()
