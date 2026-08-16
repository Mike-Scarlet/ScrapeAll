
import json
import time
from datetime import datetime
from enum import IntEnum
from typing import Optional, Sequence

from python_general_lib.database.sqlite3_wrap.multiple_models_sqlite_database import \
    MultipleModelsSQLiteDatabase

from scrape_all.sites.cangku.history import PostRef, now_utc, parse_time, to_iso
from scrape_all.storage.models import PostItem, ScrapeMeta


class Stat(IntEnum):
  """帖子处理状态机；帖子被更新时重置回 DISCOVERED 重走全程"""
  DISCOVERED = 0    # 刚被 walk 出来，仅有列表 meta
  FETCHED = 1       # 帖子页已抓取保存
  PARSED = 2        # 已解析（含非目标帖，links 为空）
  CONSUMED = 3      # 解析结果已交后续流程处理（终态）
  FETCH_FAILED = -1
  PARSE_FAILED = -2


def history_done_key(user_id: str) -> str:
  """历史回填完成标志：只有自然触底（reached_cutoff/empty_page）才置位。
  置位前已覆盖帖不触发停页（中断重跑要把更深的页抓完），置位后增量跑
  遇到 (url+时间戳) 都已记录的帖子即停。"""
  return f"yejiang:{user_id}:history_done"


class PostStore:
  """cangku 抓取状态落库：帖子去重（url 主键 + 时间戳比对）、stat 流转、回填标志"""

  def __init__(self, db_path: str):
    self.db = MultipleModelsSQLiteDatabase(db_path, [PostItem, ScrapeMeta])
    self.db.Initiate()

  def __enter__(self) -> "PostStore":
    return self

  def __exit__(self, exc_type, exc, tb):
    self.close()

  def known_times(self) -> dict[str, Optional[datetime]]:
    """库内 url -> 已记录时间戳（post_time 归一化过，可直接比较；解析失败为 None）"""
    rows = self.db.RawSelectFieldFromTableWithReturnFieldName(PostItem, ["url", "post_time"])
    return {row["url"]: parse_time(row["post_time"]) for row in rows}

  def upsert_posts(self, new_refs: Sequence[PostRef], updated_refs: Sequence[PostRef] = (),
                   now: Optional[float] = None,
                   now_dt: Optional[datetime] = None) -> tuple[int, int]:
    """collect 阶段写入。新帖插入（stat=DISCOVERED）；更新帖刷新 meta 并把
    处理状态重置回 DISCOVERED、清空 links（重新走一遍后续流程）。
    已覆盖帖（url+时间戳都没变）由 plan_page 过滤，不会进到这里。
    返回 (新帖数, 更新帖数)。now 为 epoch 秒（first/last_seen 用），
    now_dt 为相对时间解析基准。"""
    if now is None:
      now = time.time()
    if now_dt is None:
      now_dt = now_utc()
    known = self.known_times()

    def norm_time(ref: PostRef) -> str:
      t = parse_time(ref.time_text, now_dt)
      return to_iso(t) if t else (ref.time_text or "")

    new_items = []
    for ref in new_refs:
      if ref.url in known:
        continue
      new_items.append(PostItem(
          url=ref.url, title=ref.title, post_time=norm_time(ref),
          stat=int(Stat.DISCOVERED), links_json="", first_seen=now, last_seen=now))
      known[ref.url] = parse_time(ref.time_text, now_dt)
    if new_items:
      self.db.InsertBatch(new_items, on_conflict="OR IGNORE")

    for ref in updated_refs:
      item = PostItem(url=ref.url)
      item.title = ref.title
      item.post_time = norm_time(ref)
      item.stat = int(Stat.DISCOVERED)
      item.links_json = ""
      item.last_seen = now
      self.db.RecordFieldChanged(item, ["title", "post_time", "stat", "links_json", "last_seen"])
    self.db.Commit()
    return len(new_items), len(updated_refs)

  # ---- fetch / parse / consume 各阶段的取队与状态流转 ----

  def pending_fetch(self) -> list[PostItem]:
    """待抓取帖子页的帖子（DISCOVERED）"""
    return self.db.QueryRecords(PostItem, where="stat = ?", params=(int(Stat.DISCOVERED),))

  def mark_fetched(self, url: str):
    item = PostItem(url=url, stat=int(Stat.FETCHED))
    self.db.RecordFieldChanged(item, ["stat"])

  def mark_fetch_failed(self, url: str):
    item = PostItem(url=url, stat=int(Stat.FETCH_FAILED))
    self.db.RecordFieldChanged(item, ["stat"])

  def pending_parse(self) -> list[PostItem]:
    """待解析的帖子（FETCHED，页面已存本地，可离线重试）"""
    return self.db.QueryRecords(PostItem, where="stat = ?", params=(int(Stat.FETCHED),))

  def save_parsed(self, url: str, links: list, stat: int = int(Stat.PARSED)):
    """parse 阶段写入筛选结果；links 为 PanLink 的 dict 列表"""
    item = PostItem(url=url)
    item.links_json = json.dumps(links, ensure_ascii=False)
    item.stat = stat
    self.db.RecordFieldChanged(item, ["links_json", "stat"])

  def mark_parse_failed(self, url: str):
    item = PostItem(url=url, stat=int(Stat.PARSE_FAILED))
    self.db.RecordFieldChanged(item, ["stat"])

  def mark_consumed(self, url: str):
    item = PostItem(url=url, stat=int(Stat.CONSUMED))
    self.db.RecordFieldChanged(item, ["stat"])

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
