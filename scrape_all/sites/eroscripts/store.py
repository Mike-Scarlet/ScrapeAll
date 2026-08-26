
import json
import time
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional, Sequence
from urllib.parse import urlsplit

from python_general_lib.database.sqlite3_wrap.multiple_models_sqlite_database import \
    MultipleModelsSQLiteDatabase

from scrape_all.sites.eroscripts.history import TopicRef, parse_iso, to_iso
from scrape_all.storage.models import EroLink, EroTopicItem, ScrapeMeta


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


# ---- 链接级状态（EroLink，consume 阶段） ----
# probe_status：探活证据（与 downloader ProbeResult.status 同词表）
PROBE_PENDING, PROBE_ALIVE, PROBE_DEAD = "pending", "alive", "dead"
PROBE_NEEDS_AUTH, PROBE_PAYWALL, PROBE_UNKNOWN = "needs_auth", "paywall", "unknown"
# dl_status：处置结果；非终态仅 pending / failed
DL_PENDING, DL_FAILED = "pending", "failed"
DL_DOWNLOADED, DL_SKIPPED, DL_DEAD = "downloaded", "skipped", "dead"
DL_MANUAL, DL_EXHAUSTED = "manual", "exhausted"
DL_FINAL = frozenset({DL_DOWNLOADED, DL_SKIPPED, DL_DEAD, DL_MANUAL, DL_EXHAUSTED})
DL_ALL = DL_FINAL | {DL_PENDING, DL_FAILED}
# 失败后允许重试 1 次（共 2 次尝试），仍失败转 exhausted（与 manual 分开：不预期人看）
LINK_MAX_RETRY = 1


def tag_slug_from_url(tag_url: str) -> str:
  """/tag/loli/68 -> loli（剥掉尾部的 tag id 后缀）"""
  parts = tag_url.rstrip("/").split("/")
  return parts[-2] if len(parts) >= 2 else tag_url


def _now_iso() -> str:
  """当前 UTC 时间，与 to_iso 同格式（naive、截断到秒）"""
  return to_iso(datetime.now(timezone.utc).replace(tzinfo=None))


def history_done_key(tag_slug: str) -> str:
  """历史回填完成标志：只有自然触底（reached_cutoff/empty_page）才置位。
  置位前已覆盖帖不触发停页（中断重跑要把更深的页抓完），置位后增量跑
  遇到 (topic_id+bumped_at) 都已记录的帖子即停。"""
  return f"eros:tag:{tag_slug}:history_done"


class TopicStore:
  """eroscripts 抓取状态落库：topic 去重（topic_id 主键 + bumped_at 比对）、
  stat 流转、回填标志。独立 db 文件，不与 cangku 混。"""

  def __init__(self, db_path: str):
    self.db = MultipleModelsSQLiteDatabase(db_path, [EroTopicItem, EroLink, ScrapeMeta])
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

  def pending_parse(self, include_deferred: bool = False,
                    include_parsed: bool = False) -> list[EroTopicItem]:
    """待解析：FETCHED（+DEFERRED 重试 / +PARSED 离线重分类，--reparse 用）"""
    stats = [int(Stat.FETCHED)]
    if include_deferred:
      stats.append(int(Stat.DEFERRED))
    if include_parsed:
      stats.append(int(Stat.PARSED))
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

  def mark_out_of_scope_batch(self, topic_ids: Sequence[int]):
    for topic_id in topic_ids:
      item = EroTopicItem(topic_id=topic_id, stat=int(Stat.OUT_OF_SCOPE))
      self.db.RecordFieldChanged(item, ["stat"])
    self.db.Commit()

  def stat_counts(self) -> dict[int, int]:
    """stat -> 数量，跑完汇报用"""
    rows = self.db.RawSelectFieldFromTableWithReturnFieldName(EroTopicItem, ["stat"])
    counts = {}
    for row in rows:
      counts[row["stat"]] = counts.get(row["stat"], 0) + 1
    return counts

  def mark_consumed(self, topic_id: int):
    item = EroTopicItem(topic_id=topic_id, stat=int(Stat.CONSUMED))
    self.db.RecordFieldChanged(item, ["stat"])
    self.db.Commit()

  # ---- 链接级状态机（consume 阶段，EroLink） ----

  @staticmethod
  def _host_of(url: str) -> str:
    """剥 www. 的 netloc（与 topic_parse / adapters.base.host_of 同规则，内联避免依赖方向纠缠）"""
    netloc = urlsplit(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc

  def upsert_links(self, topic_id: int, links: Sequence[dict],
                   adapter_hosts: frozenset) -> int:
    """parse 后登记链接。url 主键幂等：已存在的行不动状态（重跑 parse 不清进度），
    新行按 kind / host 初始化处置：
      source/other            -> skipped（非下载目标；other 将来跟内容站时人工渠道改回）
      script/media 无 adapter -> manual（人工清单）
      其余                    -> pending 走 probe/download 流水
    返回新建行数。"""
    existing = {row.url for row in self.db.QueryRecords(EroLink)}
    new_items = []
    for l in links:
      url = (l or {}).get("url") or ""
      if not url or url in existing:
        continue
      host = self._host_of(url)
      kind = l.get("kind") or "other"
      dl_status, note = DL_PENDING, ""
      if kind in ("source", "other"):
        dl_status = DL_SKIPPED
        note = "source 流媒体出处，非下载目标" if kind == "source" else "other 内容站，跟否待决策"
      elif host not in adapter_hosts:
        dl_status = DL_MANUAL
        note = "无 adapter，人工处理"
      new_items.append(EroLink(
          url=url, host=host, kind=kind, dl_status=dl_status, dl_note=note,
          first_topic_id=topic_id))
      existing.add(url)
    if new_items:
      self.db.InsertBatch(new_items, on_conflict="OR IGNORE")
      self.db.Commit()
    return len(new_items)

  def pending_probe_links(self, limit: Optional[int] = None) -> list[EroLink]:
    """待探活：pending，或 unknown 且重试未耗尽（LINK_MAX_RETRY 次内可再探）"""
    rows = self.db.QueryRecords(EroLink, where=(
        "probe_status = ? or (probe_status = ? and probe_retries <= ?)"),
        params=(PROBE_PENDING, PROBE_UNKNOWN, LINK_MAX_RETRY))
    return rows[:limit] if limit else rows

  def pending_download_links(self, limit: Optional[int] = None) -> list[EroLink]:
    """待下载：探活 alive 且 dl 未处理，或 failed 且重试未耗尽"""
    rows = self.db.QueryRecords(EroLink, where=(
        "probe_status = ? and (dl_status = ? or (dl_status = ? and dl_retries <= ?))"),
        params=(PROBE_ALIVE, DL_PENDING, DL_FAILED, LINK_MAX_RETRY))
    return rows[:limit] if limit else rows

  def _require_link(self, url: str) -> EroLink:
    row = self.db.QueryOne(EroLink, where="url = ?", params=(url,))
    if row is None:
      raise ValueError(f"链接未登记: {url}（须先 upsert_links）")
    return row

  def mark_probe(self, url: str, status: str, meta: Optional[dict] = None,
                 note: str = ""):
    """probe 结果落库并驱动处置状态：
      alive -> 等下载；dead -> dl dead；needs_auth -> dl manual；paywall -> dl skipped；
      unknown -> 重试计数 +1，超过上限转 exhausted。"""
    row = self._require_link(url)
    item = EroLink(url=url)
    fields = ["probe_status", "probe_at"]
    item.probe_status = status
    item.probe_at = _now_iso()
    if meta:
      item.meta_json = json.dumps(meta, ensure_ascii=False)
      fields.append("meta_json")
    dl_status, dl_note = None, ""
    if status == PROBE_DEAD:
      dl_status, dl_note = DL_DEAD, note or "probe 判死"
    elif status == PROBE_NEEDS_AUTH:
      dl_status, dl_note = DL_MANUAL, note or "需登录，转人工"
    elif status == PROBE_PAYWALL:
      dl_status, dl_note = DL_SKIPPED, note or "paywall，明确放弃"
    if status == PROBE_UNKNOWN:
      item.probe_retries = row.probe_retries + 1
      fields.append("probe_retries")
      if item.probe_retries > LINK_MAX_RETRY:
        dl_status, dl_note = DL_EXHAUSTED, note or "probe unknown 重试耗尽"
    if dl_status is not None:
      item.dl_status = dl_status
      item.dl_note = dl_note
      item.dl_at = _now_iso()
      fields += ["dl_status", "dl_note", "dl_at"]
    self.db.RecordFieldChanged(item, fields)
    self.db.Commit()

  def mark_download(self, url: str, status: str, path: str = "",
                    size: int = 0, note: str = ""):
    """download 结果落库：downloaded/skipped/dead/manual 直落；failed 重试计数 +1，
    超过上限转 exhausted。"""
    if status not in (DL_DOWNLOADED, DL_SKIPPED, DL_DEAD, DL_MANUAL, DL_FAILED):
      raise ValueError(f"非法 download 状态: {status}")
    self._require_link(url)
    item = EroLink(url=url)
    fields = ["dl_status", "dl_at"]
    item.dl_status = status
    item.dl_at = _now_iso()
    if status == DL_FAILED:
      row = self._require_link(url)
      item.dl_retries = row.dl_retries + 1
      fields.append("dl_retries")
      if item.dl_retries > LINK_MAX_RETRY:
        item.dl_status = DL_EXHAUSTED
    if path:
      item.dl_path, fields = path, fields + ["dl_path"]
    if size:
      item.dl_size, fields = size, fields + ["dl_size"]
    if note:
      item.dl_note, fields = note, fields + ["dl_note"]
    self.db.RecordFieldChanged(item, fields)
    self.db.Commit()

  def set_link_status(self, url: str, dl_status: str, path: str = "",
                      size: int = 0, note: str = ""):
    """人工介入渠道（scripts/ero_links.py set 背后）：改任意合法 dl_status。
    改回 pending 视为重走自动流程——dl_retries 清零，probe 侧若已 unknown 连带
    重置（alive/dead 等探活证据保留）。path/size/note 不传不动。"""
    if dl_status not in DL_ALL:
      raise ValueError(f"非法 dl_status: {dl_status}（可选 {sorted(DL_ALL)}）")
    row = self._require_link(url)
    item = EroLink(url=url)
    fields = ["dl_status", "dl_at"]
    item.dl_status = dl_status
    item.dl_at = _now_iso()
    if dl_status == DL_PENDING:
      item.dl_retries = 0
      fields.append("dl_retries")
      if row.probe_status == PROBE_UNKNOWN:
        item.probe_status, item.probe_retries = PROBE_PENDING, 0
        fields += ["probe_status", "probe_retries"]
    if path:
      item.dl_path, fields = path, fields + ["dl_path"]
    if size:
      item.dl_size, fields = size, fields + ["dl_size"]
    if note:
      item.dl_note, fields = note, fields + ["dl_note"]
    self.db.RecordFieldChanged(item, fields)
    self.db.Commit()

  def topic_consume_state(self, topic_id: int) -> str:
    """topic 是否可判 CONSUMED：'ready'（全部链接 dl 终态，或无链接）/ 'pending'
    （还有非终态）/ 'unregistered'（links 未登记进 EroLink，编排须先 upsert）。"""
    topic = self.db.QueryOne(EroTopicItem, where="topic_id = ?", params=(topic_id,))
    if topic is None:
      raise ValueError(f"topic 不存在: {topic_id}")
    try:
      urls = [(l or {}).get("url") or "" for l in json.loads(topic.links_json or "[]")]
    except ValueError:
      urls = []
    urls = [u for u in urls if u]
    if not urls:
      return "ready"
    marks = ",".join("?" for _ in urls)
    rows = self.db.QueryRecords(EroLink, where=f"url in ({marks})", params=tuple(urls))
    if len(rows) < len(set(urls)):
      return "unregistered"
    return "ready" if all(r.dl_status in DL_FINAL for r in rows) else "pending"

  def link_status_counts(self) -> dict[str, int]:
    """dl_status -> 数量，跑完汇报用"""
    rows = self.db.RawSelectFieldFromTableWithReturnFieldName(EroLink, ["dl_status"])
    counts: dict[str, int] = {}
    for row in rows:
      counts[row["dl_status"]] = counts.get(row["dl_status"], 0) + 1
    return counts

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
