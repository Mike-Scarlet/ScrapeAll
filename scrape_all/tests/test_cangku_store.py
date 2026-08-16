
import json
from datetime import datetime

from scrape_all.sites.cangku.history import PostRef
from scrape_all.sites.cangku.store import PostStore, Stat
from scrape_all.storage.models import PostItem


def make_store(tmp_path):
  return PostStore(str(tmp_path / "cangku_test.db"))

def get_item(store, url):
  return store.db.QueryOne(PostItem, where="url = ?", params=(url,))


def test_upsert_posts_insert_new_normalized(tmp_path):
  with make_store(tmp_path) as store:
    n_new, n_upd = store.upsert_posts(
        [PostRef("u1", "t1", "2026-08-13T13:48:00.000Z")], now=1000.0)
    assert (n_new, n_upd) == (1, 0)
    item = get_item(store, "u1")
    assert item.post_time == "2026-08-13 13:48:00"    # 归一化，known_times 可直接比较
    assert item.stat == Stat.DISCOVERED
    # 解析不了的时间存原文，不丢
    store.upsert_posts([PostRef("u2", "t2", "昨天")], now=1000.0,
                       now_dt=datetime(2026, 8, 16))
    assert get_item(store, "u2").post_time == "昨天"


def test_known_times(tmp_path):
  with make_store(tmp_path) as store:
    store.upsert_posts([PostRef("u1", "t1", "2026-08-13T13:48:00.000Z"),
                        PostRef("u2", "t2", "昨天")], now_dt=datetime(2026, 8, 16))
    known = store.known_times()
    assert known["u1"] == datetime(2026, 8, 13, 13, 48)
    assert known["u2"] is None


def test_upsert_posts_idempotent_rerun(tmp_path):
  with make_store(tmp_path) as store:
    store.upsert_posts([PostRef("u1", "t1", "2026-08-10")], now=1000.0)
    # 已覆盖帖（url+时间戳都没变）不产生重复行、不动状态
    n_new, n_upd = store.upsert_posts([PostRef("u1", "t1", "2026-08-10")], now=2000.0)
    assert (n_new, n_upd) == (0, 0)
    item = get_item(store, "u1")
    assert item.first_seen == 1000.0 and item.last_seen == 1000.0
    assert item.stat == Stat.DISCOVERED


def test_upsert_updated_resets_state(tmp_path):
  with make_store(tmp_path) as store:
    store.upsert_posts([PostRef("u1", "t1", "2026-08-01")], now=1000.0)
    store.save_parsed("u1", [{"name": "n", "url": "u", "pwd": "", "pan_type": "baidu"}])
    assert get_item(store, "u1").stat == Stat.PARSED

    n_new, n_upd = store.upsert_posts(
        [], [PostRef("u1", "t1-new", "2026-08-15")], now=2000.0)
    assert (n_new, n_upd) == (0, 1)
    item = get_item(store, "u1")
    assert item.title == "t1-new"
    assert item.post_time == "2026-08-15 00:00:00"
    assert item.stat == Stat.DISCOVERED and item.links_json == ""   # 重置，重新走流程
    assert item.first_seen == 1000.0 and item.last_seen == 2000.0   # 首见时间不重置


def test_stat_lifecycle(tmp_path):
  with make_store(tmp_path) as store:
    store.upsert_posts([PostRef("u1", "t1", "2026-08-10"),
                        PostRef("u2", "t2", "2026-08-09"),
                        PostRef("u3", "t3", "2026-08-08")])
    assert {p.url for p in store.pending_fetch()} == {"u1", "u2", "u3"}

    store.mark_fetched("u1")
    store.mark_fetch_failed("u2")
    assert {p.url for p in store.pending_fetch()} == {"u3"}
    assert {p.url for p in store.pending_parse()} == {"u1"}
    assert get_item(store, "u2").stat == Stat.FETCH_FAILED

    links = [{"name": "百度网盘", "url": "https://pan.baidu.com/s/1x?pwd=ab12",
              "pwd": "ab12", "pan_type": "baidu"}]
    store.save_parsed("u1", links)
    item = get_item(store, "u1")
    assert item.stat == Stat.PARSED and json.loads(item.links_json) == links
    assert store.pending_parse() == []

    store.mark_consumed("u1")
    assert get_item(store, "u1").stat == Stat.CONSUMED

    store.mark_fetched("u3")
    store.mark_parse_failed("u3")
    assert get_item(store, "u3").stat == Stat.PARSE_FAILED


def test_mark_out_of_scope(tmp_path):
  with make_store(tmp_path) as store:
    store.upsert_posts([PostRef("u1", "t1", "2026-08-10")])
    store.mark_fetched("u1")
    store.mark_out_of_scope("u1")                       # 过滤判定工况外 -> 终态
    item = get_item(store, "u1")
    assert item.stat == Stat.OUT_OF_SCOPE and item.links_json == ""
    assert store.pending_parse() == []                  # 不再进解析队列


def test_history_done_flag(tmp_path):
  with make_store(tmp_path) as store:
    assert store.get_flag("yejiang:309550:history_done") is False
    store.set_flag("yejiang:309550:history_done")
    assert store.get_flag("yejiang:309550:history_done") is True
    store.clear_flag("yejiang:309550:history_done")
    assert store.get_flag("yejiang:309550:history_done") is False
