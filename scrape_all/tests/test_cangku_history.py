
from datetime import datetime

from scrape_all.sites.cangku.history import (
  PostRef, extract_time_text, parse_time, plan_page, to_iso,
)

NOW = datetime(2026, 8, 16, 12, 0, 0)


def test_extract_time_text_from_card_text():
  # probe 实测的卡片文本形态：标题 + 数字（阅读量） + 相对时间
  assert extract_time_text("[叶酱汉化][RJ01673309]标题(副标题) 3298 2 天前") == "2 天前"
  assert extract_time_text("[2D动画]合集（截至26.08） 122565 3 天前") == "3 天前"
  # 老帖分页预期的绝对日期形态
  assert extract_time_text("标题 99 2026-08-01") == "2026-08-01"
  assert extract_time_text("标题 99 2026/08/01 10:30") == "2026/08/01 10:30"
  assert extract_time_text("标题没有时间字段") is None
  assert extract_time_text("") is None


def test_card_text_time_roundtrip():
  text = "[标题] 3298 2 天前"
  t = parse_time(extract_time_text(text), now=NOW)
  assert t == datetime(2026, 8, 14, 12, 0, 0)


def ref(url, time_text):
  return PostRef(url=url, title=f"t-{url}", time_text=time_text)


def test_parse_time_iso_from_datetime_attr():
  # post-card <time datetime="..."> 属性实测形态：Z 结尾 UTC，毫秒
  assert parse_time("2026-08-13T13:48:00.000Z") == datetime(2026, 8, 13, 13, 48)
  assert parse_time("2026-08-13T13:48:00Z") == datetime(2026, 8, 13, 13, 48)
  # 带时区偏移的转成 naive UTC："13:48+08:00" 即 UTC 05:48
  assert parse_time("2026-08-13T13:48:00+08:00") == datetime(2026, 8, 13, 5, 48)
  # 无时区的 ISO 原样按 naive 用
  assert parse_time("2026-08-13T13:48:00") == datetime(2026, 8, 13, 13, 48)
  assert parse_time("2026-08-13T13:48:00.000+00:00").tzinfo is None
  # 坏 ISO 不抛错
  assert parse_time("T-这不是时间") is None


def test_parse_time_absolute_formats():
  assert parse_time("2026-08-01 10:30:00") == datetime(2026, 8, 1, 10, 30, 0)
  assert parse_time("2026-08-01 10:30") == datetime(2026, 8, 1, 10, 30)
  assert parse_time("2026-08-01") == datetime(2026, 8, 1)
  assert parse_time("2026/08/01 10:30") == datetime(2026, 8, 1, 10, 30)
  assert parse_time("2026/08/01") == datetime(2026, 8, 1)
  assert parse_time("  2026-08-01 10:30  ") == datetime(2026, 8, 1, 10, 30)   # 带空白


def test_parse_time_relative_with_fixed_now():
  assert parse_time("3天前", now=NOW) == datetime(2026, 8, 13, 12, 0, 0)
  assert parse_time("2小时前", now=NOW) == datetime(2026, 8, 16, 10, 0, 0)
  assert parse_time("5分钟前", now=NOW) == datetime(2026, 8, 16, 11, 55)
  assert parse_time("1年前", now=NOW) == datetime(2025, 8, 16, 12, 0, 0)
  assert parse_time("3 天前", now=NOW) == datetime(2026, 8, 13, 12, 0, 0)     # 数字单位间空白


def test_parse_time_garbage_returns_none():
  assert parse_time("") is None
  assert parse_time(None) is None
  assert parse_time("昨天") is None
  assert parse_time("2026-08-01 10:30:00", now=None) == datetime(2026, 8, 1, 10, 30)
  assert parse_time("3天前", now=None) is None    # 相对时间必须有 now


def test_to_iso_roundtrip():
  t = datetime(2026, 8, 16, 12, 0, 0)
  assert to_iso(t) == "2026-08-16 12:00:00"
  assert parse_time(to_iso(t)) == t
  assert parse_time(to_iso(t.replace(microsecond=500))) == t    # 固定到秒


def test_plan_page_empty_page_stops():
  d = plan_page([])
  assert d.new_refs == [] and d.updated_refs == []
  assert not d.should_continue and d.stop_reason == "empty_page"


def test_plan_page_no_cutoff_no_known_keeps_all():
  refs = [ref("a", "2026-08-10"), ref("b", "2026-08-01")]
  d = plan_page(refs)
  assert d.new_refs == refs and d.updated_refs == []
  assert d.should_continue and d.stop_reason == ""


def test_plan_page_cutoff_cuts_mid_page():
  refs = [
    ref("a", "2026-08-10"),
    ref("b", "2026-08-02"),
    ref("c", "2026-08-01"),   # == cutoff，含该时刻，保留
    ref("d", "2026-07-01"),
  ]
  d = plan_page(refs, cutoff=datetime(2026, 8, 1))
  assert [r.url for r in d.new_refs] == ["a", "b", "c"]
  assert d.updated_refs == []
  assert not d.should_continue and d.stop_reason == "reached_cutoff"


def test_plan_page_cutoff_boundary_inclusive():
  refs = [ref("a", "2026-08-01")]
  d = plan_page(refs, cutoff=datetime(2026, 8, 1))       # 恰好等于 cutoff：含
  assert [r.url for r in d.new_refs] == ["a"] and d.should_continue
  d = plan_page(refs, cutoff=datetime(2026, 8, 1, 0, 0, 1))   # 早于 cutoff 才截断
  assert d.new_refs == [] and not d.should_continue and d.stop_reason == "reached_cutoff"


def test_plan_page_known_stops_incremental():
  refs = [ref("a", "2026-08-10"), ref("b", "2026-08-09")]
  # url+时间戳都与库内一致 -> 覆盖边界，停；边界之后的新帖 b 仍要收集
  d = plan_page(refs, known={"a": datetime(2026, 8, 10)})
  assert [r.url for r in d.new_refs] == ["b"]
  assert not d.should_continue and d.stop_reason == "known_boundary"
  # 边界出现在第二张卡：更上面的 a 是新帖
  d = plan_page(refs, known={"b": datetime(2026, 8, 9)})
  assert [r.url for r in d.new_refs] == ["a"]
  assert not d.should_continue and d.stop_reason == "known_boundary"


def test_plan_page_backfill_continues_on_known():
  refs = [ref("a", "2026-08-10"), ref("b", "2026-08-01")]
  known = {"a": datetime(2026, 8, 10), "b": datetime(2026, 8, 1)}
  # 回填模式：整页都已覆盖也要继续翻（更深的页还有没抓的历史）
  d = plan_page(refs, known=known, stop_on_known=False)
  assert d.new_refs == [] and d.updated_refs == []
  assert d.should_continue and d.stop_reason == ""
  # 回填模式遇到老帖仍然自然触底
  d = plan_page(refs, cutoff=datetime(2026, 8, 5), known=known, stop_on_known=False)
  assert not d.should_continue and d.stop_reason == "reached_cutoff"


def test_plan_page_updated_post_requeued():
  # 库里有 a（08-01），列表里 a 时间变 08-10：被作者更新，重新进队
  d = plan_page([ref("a", "2026-08-10")], known={"a": datetime(2026, 8, 1)})
  assert d.new_refs == [] and [r.url for r in d.updated_refs] == ["a"]
  assert d.should_continue and d.stop_reason == ""


def test_plan_page_updated_collected_even_after_boundary():
  # 边界（b 已覆盖）之后本页不再有新帖，但同页更上方的更新帖照常收集
  refs = [ref("a", "2026-08-10"), ref("b", "2026-08-09")]
  known = {"a": datetime(2026, 8, 1), "b": datetime(2026, 8, 9)}
  d = plan_page(refs, known=known)
  assert [r.url for r in d.updated_refs] == ["a"] and d.new_refs == []
  assert not d.should_continue and d.stop_reason == "known_boundary"


def test_plan_page_unparsable_time():
  # url 未知 + 时间解析不了：保留（不丢数据），不参与停页判断
  d = plan_page([ref("a", "昨天"), ref("b", "2026-07-01")], cutoff=datetime(2026, 8, 1))
  assert [r.url for r in d.new_refs] == ["a"]
  assert d.stop_reason == "reached_cutoff"
  # url 已见 + 任一侧时间解析不了：无从比较，按已覆盖处理
  d = plan_page([ref("a", "昨天")], known={"a": datetime(2026, 8, 1)})
  assert d.new_refs == [] and d.updated_refs == [] and d.stop_reason == "known_boundary"
  d = plan_page([ref("a", "2026-08-10")], known={"a": None})
  assert d.stop_reason == "known_boundary"


def test_plan_page_relative_time_uses_now():
  refs = [ref("a", "3天前"), ref("b", "10天前")]
  d = plan_page(refs, cutoff=datetime(2026, 8, 10), now=NOW)
  assert [r.url for r in d.new_refs] == ["a"]        # 3天前=08-13 保留；10天前=08-06 截断
  assert not d.should_continue and d.stop_reason == "reached_cutoff"
