
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional, Sequence

# 纯逻辑模块：不依赖 playwright，用假页数据即可单测（见 tests/）

# 站点常见绝对时间格式，probe 后按实际 DOM 增删
TIME_FORMATS = [
  "%Y-%m-%d %H:%M:%S",
  "%Y-%m-%d %H:%M",
  "%Y-%m-%d",
  "%Y/%m/%d %H:%M",
  "%Y/%m/%d",
]

# 相对时间：3分钟前 / 2小时前 / 5天前 / 3个月前（月=30天、年=365天，近似够用）
RELATIVE_TIME_RE = re.compile(r"(\d+)\s*(秒|分钟|分|小时|时|天|日|周|月|年)前")
RELATIVE_UNITS = {
  "秒": timedelta(seconds=1),
  "分钟": timedelta(minutes=1),
  "分": timedelta(minutes=1),
  "小时": timedelta(hours=1),
  "时": timedelta(hours=1),
  "天": timedelta(days=1),
  "日": timedelta(days=1),
  "周": timedelta(weeks=1),
  "月": timedelta(days=30),
  "年": timedelta(days=365),
}


def parse_time(text: Optional[str], now: Optional[datetime] = None) -> Optional[datetime]:
  """页面时间文本 -> naive UTC datetime；解析不了返回 None（不抛错）

  优先 <time datetime="..."> 的 ISO 8601 属性（精确到秒）；
  相对时间"3 天前"是兜底（需 now，天级精度）。全模块统一用 naive UTC 做比较。
  """
  if not text:
    return None
  text = text.strip()
  if "T" in text:   # ISO 8601："2026-08-13T13:48:00.000Z" / 带 +08:00 偏移
    try:
      dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
      return None
    if dt.tzinfo is not None:
      dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
  for fmt in TIME_FORMATS:
    try:
      return datetime.strptime(text, fmt)
    except ValueError:
      pass
  m = RELATIVE_TIME_RE.fullmatch(text)
  if m and now is not None:
    return now - int(m.group(1)) * RELATIVE_UNITS[m.group(2)]
  return None


# post-card 文本尾部的时间片段："标题 3298 2 天前" -> "2 天前"；老帖分页可能是绝对日期
TIME_TAIL_RE = re.compile(
    r"(\d+\s*(?:秒|分钟|分|小时|时|天|日|周|月|年)前"
    r"|\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)$")


def extract_time_text(text: Optional[str]) -> Optional[str]:
  """从卡片整段文本里抠出结尾的时间片段，抠不到返回 None"""
  if not text:
    return None
  m = TIME_TAIL_RE.search(text.strip())
  return m.group(1) if m else None


@dataclass
class PostRef:
  """列表页一张 post-card 解析出的帖子引用"""
  url: str
  title: str
  time_text: Optional[str] = None


@dataclass
class PageDecision:
  """plan_page 对一页帖子的决策"""
  new_refs: list[PostRef]
  updated_refs: list[PostRef]
  should_continue: bool
  stop_reason: str = ""    # empty_page / reached_cutoff / known_boundary / ""=继续


def ref_time(ref: PostRef, now: Optional[datetime] = None) -> Optional[datetime]:
  return parse_time(ref.time_text, now)


def plan_page(refs: Sequence[PostRef],
              cutoff: Optional[datetime] = None,
              known: Optional[Mapping[str, Optional[datetime]]] = None,
              now: Optional[datetime] = None,
              stop_on_known: bool = True) -> PageDecision:
  """对一页帖子分流（新帖 / 更新帖 / 已覆盖）并决定是否继续翻页。

  前提：refs 按时间从新到老排（列表页天然如此）。known 为库内已记录的
  url -> 时间戳（解析失败为 None）。cutoff 为历史下界（含该时刻：
  "抓到 2025-12-01" 即 2025-12-01 00:00 之后的帖都要，恰好等于下界的保留）。

  分流规则（按序）：
    时间 < cutoff -> 丢弃并触底（再往后只会更老）
    url 不在 known -> 新帖
    url 在 known 且时间比库内新 -> 帖子被作者更新过，重新进队（重置重走）
    url 在 known 且时间不比库内新（或任一侧无从比较）-> 已覆盖
  停页规则：
    空页 -> 停
    页内出现 < cutoff 的帖子 -> 停（reached_cutoff）
    页内出现已覆盖帖子 -> stop_on_known 决定：增量模式停（known_boundary，
      第一个重复的 url+时间戳就是覆盖边界，更深只会更老），回填模式继续
      （此前中断过，更深的页还有没抓的历史）。
      边界触发后仍扫完本页：边界之后不会再有新帖，但可能还有更新帖
      （更新帖时间戳变新会上浮，不会被边界挡住）。
  """
  if not refs:
    return PageDecision([], [], False, "empty_page")
  known = known or {}

  new_refs = []
  updated_refs = []
  crossed = False
  boundary = False
  for ref in refs:
    # 触底判断先于已覆盖判断：已见过的老帖同样说明边界已过（更深的页只会更老）
    t = ref_time(ref, now)
    if cutoff is not None and t is not None and t < cutoff:
      crossed = True
      continue
    if ref.url not in known:
      new_refs.append(ref)
      continue
    stored = known[ref.url]
    if t is not None and stored is not None and t > stored:
      updated_refs.append(ref)
    else:
      boundary = True

  if crossed:
    return PageDecision(new_refs, updated_refs, False, "reached_cutoff")
  if boundary and stop_on_known:
    return PageDecision(new_refs, updated_refs, False, "known_boundary")
  return PageDecision(new_refs, updated_refs, True, "")


def to_iso(t: datetime) -> str:
  """时间戳统一序列化格式：naive UTC、固定到秒，parse_time 可直接读回"""
  return t.replace(microsecond=0).isoformat(sep=" ")


def now_utc() -> datetime:
  """当前 naive UTC（本模块统一用 naive UTC 做比较）"""
  return datetime.now(timezone.utc).replace(tzinfo=None)
