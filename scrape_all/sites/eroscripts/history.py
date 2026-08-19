
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Optional, Sequence

# 纯逻辑模块：时间归一化 + tag 列表翻页决策，不依赖 playwright（fixture 单测）
# walk/增量比较统一用 bumped_at（tag 列表的排序键）：任何回复都会把 topic 顶起，
# bumped_at 变新 = 该 topic 有新动态，重置处理状态重走流程。


def parse_iso(text: Optional[str]) -> Optional[datetime]:
  """Discourse ISO 8601（"2026-08-15T15:02:59.696Z" / 带偏移）-> naive UTC；失败返回 None

  统一截断到秒（与 to_iso 序列化精度一致）：否则库内秒级 bumped_at 和
  原始毫秒级 bumped_at 比较会把同一帖永远误判为被顶起。
  """
  if not text:
    return None
  try:
    dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
  except ValueError:
    return None
  if dt.tzinfo is not None:
    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
  return dt.replace(microsecond=0)


def to_iso(t: datetime) -> str:
  """时间戳统一序列化格式：naive UTC、固定到秒"""
  return t.replace(microsecond=0).isoformat(sep=" ")


def parse_cutoff(text: str) -> Optional[datetime]:
  """cutoff 文本（"2026-03-01"）-> naive UTC datetime；也接受完整 ISO"""
  try:
    return datetime.strptime(text.strip(), "%Y-%m-%d")
  except ValueError:
    return parse_iso(text)


@dataclass
class TopicRef:
  """tag 列表页一条 topic 的解析结果"""
  topic_id: int
  url: str
  title: str
  author: str = ""
  created_at: str = ""          # 站内原始 ISO 文本，落库前归一化
  bumped_at: str = ""           # 站内原始 ISO 文本，walk/增量比较用
  tags: tuple[str, ...] = ()
  category_id: int = 0
  posts_count: int = 0
  views: int = 0
  pinned: bool = False


def ref_time(ref: TopicRef) -> Optional[datetime]:
  return parse_iso(ref.bumped_at)


@dataclass
class PageDecision:
  """plan_page 对一页 topics 的决策"""
  new_refs: list[TopicRef] = field(default_factory=list)
  updated_refs: list[TopicRef] = field(default_factory=list)
  should_continue: bool = True
  stop_reason: str = ""    # empty_page / reached_cutoff / known_boundary / ""=继续


def plan_page(refs: Sequence[TopicRef],
              cutoff: Optional[datetime] = None,
              known: Optional[Mapping[int, Optional[datetime]]] = None,
              stop_on_known: bool = True) -> PageDecision:
  """对一页 topics 分流（新帖 / 更新帖 / 已覆盖）并决定是否继续翻页。

  前提：refs 按 bumped_at 从新到老排（tag 列表天然如此）。known 为库内已记录的
  topic_id -> bumped_at（解析失败为 None）。cutoff 为历史下界（含该时刻）。

  分流规则（按序，同 cangku collect 语义）：
    bumped_at < cutoff -> 丢弃并触底（再往后只会更老）
    topic_id 不在 known -> 新帖
    topic_id 在 known 且 bumped_at 比库内新 -> 被顶起过，重新进队（重置重走）
    topic_id 在 known 且不比库内新（或无从比较）-> 已覆盖
  停页规则：
    空页 -> 停；页内出现 < cutoff -> 停（reached_cutoff）；
    页内出现已覆盖 -> stop_on_known 决定（增量停 / 回填继续），边界后仍扫完本页。
  pinned 帖不受排序保证约束（永远浮在页首）：不参与触底/边界判定，正常参与新/更新分流。
  """
  if not refs:
    return PageDecision([], [], False, "empty_page")
  known = known or {}

  new_refs = []
  updated_refs = []
  crossed = False
  boundary = False
  for ref in refs:
    t = ref_time(ref)
    if not ref.pinned and cutoff is not None and t is not None and t < cutoff:
      crossed = True
      continue
    if ref.topic_id not in known:
      new_refs.append(ref)
      continue
    stored = known[ref.topic_id]
    if t is not None and stored is not None and t > stored:
      updated_refs.append(ref)
    elif not ref.pinned:
      boundary = True

  if crossed:
    return PageDecision(new_refs, updated_refs, False, "reached_cutoff")
  if boundary and stop_on_known:
    return PageDecision(new_refs, updated_refs, False, "known_boundary")
  return PageDecision(new_refs, updated_refs, True, "")
