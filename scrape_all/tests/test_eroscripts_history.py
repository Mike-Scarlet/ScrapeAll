
from datetime import datetime

from scrape_all.sites.eroscripts.history import (
    TopicRef, parse_cutoff, parse_iso, plan_page, ref_time, to_iso)


def ref(tid: int, bumped: str, pinned: bool = False) -> TopicRef:
  return TopicRef(topic_id=tid, url=f"https://x/t/topic/{tid}",
                  title=f"t{tid}", bumped_at=bumped, pinned=pinned)


def test_parse_iso_z_and_offset():
  assert parse_iso("2026-08-15T15:02:59.696Z") == datetime(2026, 8, 15, 15, 2, 59)
  assert parse_iso("2026-08-15T23:02:59+08:00") == datetime(2026, 8, 15, 15, 2, 59)
  assert parse_iso("") is None
  assert parse_iso(None) is None
  assert parse_iso("not a time") is None


def test_parse_cutoff():
  assert parse_cutoff("2026-03-01") == datetime(2026, 3, 1)
  assert parse_cutoff("2026-03-01T00:00:00Z") == datetime(2026, 3, 1)
  assert parse_cutoff("bad") is None


def test_to_iso_roundtrip():
  dt = parse_iso("2026-08-15T15:02:59.696Z")
  assert to_iso(dt) == "2026-08-15 15:02:59"
  assert parse_iso(to_iso(dt)) == dt


def test_ref_time_uses_bumped():
  r = ref(1, "2026-08-01T00:00:00Z")
  assert ref_time(r) == datetime(2026, 8, 1)


def test_plan_page_empty():
  d = plan_page([])
  assert not d.should_continue and d.stop_reason == "empty_page"


def test_plan_page_all_new_continues():
  d = plan_page([ref(1, "2026-08-01T00:00:00Z"), ref(2, "2026-07-01T00:00:00Z")])
  assert d.should_continue and not d.stop_reason
  assert [r.topic_id for r in d.new_refs] == [1, 2]
  assert not d.updated_refs


def test_plan_page_cutoff_crossing_stops_and_keeps_newer():
  cutoff = datetime(2026, 3, 1)
  refs = [ref(1, "2026-08-01T00:00:00Z"),
          ref(2, "2026-02-28T23:59:59Z"),   # < cutoff：触底丢弃
          ref(3, "2026-04-01T00:00:00Z")]   # 触底后仍扫完本页
  d = plan_page(refs, cutoff=cutoff)
  assert not d.should_continue and d.stop_reason == "reached_cutoff"
  assert [r.topic_id for r in d.new_refs] == [1, 3]


def test_plan_page_cutoff_inclusive_boundary():
  # cutoff 含该时刻：恰好等于下界的保留，早一秒的触底
  cutoff = datetime(2026, 3, 1)
  d = plan_page([ref(1, "2026-03-01T00:00:00Z")], cutoff=cutoff)
  assert d.should_continue and d.stop_reason == ""
  d = plan_page([ref(1, "2026-02-28T23:59:59Z")], cutoff=cutoff)
  assert d.stop_reason == "reached_cutoff" and not d.new_refs


def test_plan_page_new_updated_covered():
  known = {1: datetime(2026, 8, 1),          # 已覆盖（时间没变）
           2: datetime(2026, 7, 1),          # 被顶起（bumped 变新）
           3: None}                          # 库内时间解析失败：无从比较 -> 已覆盖
  refs = [ref(1, "2026-08-01T00:00:00Z"),
          ref(2, "2026-08-02T00:00:00Z"),
          ref(3, "2026-08-03T00:00:00Z"),
          ref(4, "2026-08-04T00:00:00Z")]
  d = plan_page(refs, known=known, stop_on_known=False)
  assert [r.topic_id for r in d.new_refs] == [4]
  assert [r.topic_id for r in d.updated_refs] == [2]
  assert d.should_continue   # 回填模式：已覆盖不停页


def test_plan_page_known_boundary_stops_incremental():
  known = {1: datetime(2026, 8, 1)}
  refs = [ref(2, "2026-08-05T00:00:00Z"),    # 新帖在已覆盖帖前面：先收进来
          ref(1, "2026-08-01T00:00:00Z"),    # 已覆盖 -> 边界
          ref(3, "2026-08-06T00:00:00Z")]    # 边界后仍扫完本页（更新帖可能上浮）
  d = plan_page(refs, known=known, stop_on_known=True)
  assert d.stop_reason == "known_boundary" and not d.should_continue
  assert [r.topic_id for r in d.new_refs] == [2, 3]


def test_plan_page_pinned_ignores_cutoff_and_boundary():
  # pinned 帖永远浮在页首，不受排序保证：老 pinned 不触底、已覆盖 pinned 不设边界
  cutoff = datetime(2026, 3, 1)
  known = {9: datetime(2026, 1, 1)}
  refs = [ref(9, "2026-01-01T00:00:00Z", pinned=True),
          ref(1, "2026-08-01T00:00:00Z")]
  d = plan_page(refs, cutoff=cutoff, known=known, stop_on_known=True)
  assert d.should_continue and d.stop_reason == ""
  assert [r.topic_id for r in d.new_refs] == [1]
