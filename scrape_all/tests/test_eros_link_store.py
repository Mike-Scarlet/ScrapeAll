import json

from scrape_all.sites.eroscripts.history import TopicRef
from scrape_all.sites.eroscripts.store import (
    DL_DEAD, DL_DOWNLOADED, DL_EXHAUSTED, DL_FAILED, DL_MANUAL, DL_PENDING,
    DL_SKIPPED, LINK_MAX_RETRY, PROBE_ALIVE, PROBE_DEAD, PROBE_NEEDS_AUTH,
    PROBE_PAYWALL, PROBE_PENDING, PROBE_UNKNOWN, Stat, TopicStore,
)
from scrape_all.storage.models import EroLink, EroTopicItem

ADAPTER_HOSTS = frozenset({
    "pixeldrain.com", "gofile.io", "mega.nz", "catbox.moe",
    "discuss.eroscripts.com",
})


def make_store(tmp_path):
  return TopicStore(str(tmp_path / "eros_test.db"))


def get_link(store, url):
  return store.db.QueryOne(EroLink, where="url = ?", params=(url,))


def link(url, kind):
  return {"url": url, "kind": kind, "name": "x", "section": "s",
          "post_number": 1, "username": "u"}


# ---- upsert_links：登记与初始化 ----

def test_upsert_links_initial_dl_status_by_kind_and_host(tmp_path):
  with make_store(tmp_path) as store:
    n = store.upsert_links(11, [
        link("https://discuss.eroscripts.com/uploads/a.funscript", "script"),
        link("https://pixeldrain.com/l/abc", "media"),
        link("https://workupload.com/file/xyz", "media"),      # 无 adapter
        link("https://iwara.tv/videos/1", "source"),
        link("https://www.patreon.com/posts/1", "other"),      # www. 剥除
    ], ADAPTER_HOSTS)
    assert n == 5
    assert get_link(store, "https://discuss.eroscripts.com/uploads/a.funscript").dl_status == DL_PENDING
    assert get_link(store, "https://pixeldrain.com/l/abc").dl_status == DL_PENDING
    wu = get_link(store, "https://workupload.com/file/xyz")
    assert (wu.dl_status, wu.dl_note) == (DL_MANUAL, "无 adapter，人工处理")
    src = get_link(store, "https://iwara.tv/videos/1")
    assert src.dl_status == DL_SKIPPED and "source" in src.dl_note
    other = get_link(store, "https://www.patreon.com/posts/1")
    assert other.dl_status == DL_SKIPPED and other.host == "patreon.com"
    # 首见 topic 溯源
    assert all(r.first_topic_id == 11 for r in store.db.QueryRecords(EroLink))


def test_upsert_links_idempotent_keeps_progress(tmp_path):
  with make_store(tmp_path) as store:
    url = "https://pixeldrain.com/l/abc"
    store.upsert_links(1, [link(url, "media")], ADAPTER_HOSTS)
    store.mark_download(url, DL_DOWNLOADED, path="a/b.zip", size=100)
    # 重跑 parse / 别的 topic 引用同 URL：状态与元信息不动，也不新建行
    n = store.upsert_links(2, [link(url, "media")], ADAPTER_HOSTS)
    assert n == 0
    row = get_link(store, url)
    assert (row.dl_status, row.dl_path, row.dl_size, row.first_topic_id) == \
        (DL_DOWNLOADED, "a/b.zip", 100, 1)


def test_upsert_links_requires_url(tmp_path):
  with make_store(tmp_path) as store:
    n = store.upsert_links(1, [{"kind": "media"}, link("https://x/1", "media")],
                           ADAPTER_HOSTS)
    assert n == 1  # 空 url 的条目跳过不炸


# ---- 取队：pending_probe_links / pending_download_links ----

def test_pending_probe_links_retry_window(tmp_path):
  with make_store(tmp_path) as store:
    urls = ["https://pixeldrain.com/l/1", "https://pixeldrain.com/l/2"]
    store.upsert_links(1, [link(u, "media") for u in urls], ADAPTER_HOSTS)
    assert [r.url for r in store.pending_probe_links()] == urls
    # unknown 一次（retries=1 <= LINK_MAX_RETRY）仍在队；两次（retries=2）出队
    store.mark_probe(urls[0], PROBE_UNKNOWN)
    assert [r.url for r in store.pending_probe_links()] == urls
    store.mark_probe(urls[0], PROBE_UNKNOWN)
    assert [r.url for r in store.pending_probe_links()] == [urls[1]]
    # dead / alive 都不再探
    store.mark_probe(urls[1], PROBE_DEAD)
    assert store.pending_probe_links() == []


def test_pending_download_links_requires_alive_and_retry_window(tmp_path):
  with make_store(tmp_path) as store:
    urls = ["https://pixeldrain.com/l/1", "https://pixeldrain.com/l/2",
            "https://pixeldrain.com/l/3"]
    store.upsert_links(1, [link(u, "media") for u in urls], ADAPTER_HOSTS)
    for u in urls:
      store.mark_probe(u, PROBE_ALIVE, meta={"filename": "f.zip", "size": 5})
    store.mark_probe("https://pixeldrain.com/l/3", PROBE_NEEDS_AUTH)
    assert [r.url for r in store.pending_download_links()] == urls[:2]
    store.mark_download(urls[0], DL_FAILED)
    assert [r.url for r in store.pending_download_links()] == urls[:2]  # failed 未耗尽仍在队
    store.mark_download(urls[0], DL_FAILED)
    assert [r.url for r in store.pending_download_links()] == [urls[1]]
    store.mark_download(urls[1], DL_DOWNLOADED)
    assert store.pending_download_links() == []


# ---- mark_probe：探活证据 -> 处置状态驱动 ----

def test_mark_probe_transitions(tmp_path):
  with make_store(tmp_path) as store:
    cases = [
        ("https://pixeldrain.com/l/dead", PROBE_DEAD, DL_DEAD),
        ("https://pixeldrain.com/l/auth", PROBE_NEEDS_AUTH, DL_MANUAL),
        ("https://pixeldrain.com/l/pay", PROBE_PAYWALL, DL_SKIPPED),
        ("https://pixeldrain.com/l/alive", PROBE_ALIVE, DL_PENDING),
    ]
    store.upsert_links(1, [link(u, "media") for u, _, _ in cases], ADAPTER_HOSTS)
    for url, probe_st, dl_st in cases:
      store.mark_probe(url, probe_st)
      assert get_link(store, url).dl_status == dl_st
    store.mark_probe("https://pixeldrain.com/l/alive", PROBE_ALIVE,
                     meta={"filename": "f.zip", "size": 5})
    row = get_link(store, "https://pixeldrain.com/l/alive")
    assert json.loads(row.meta_json) == {"filename": "f.zip", "size": 5}
    assert row.probe_at  # 时间戳落了


def test_mark_probe_unknown_exhausts_after_max_retry(tmp_path):
  with make_store(tmp_path) as store:
    url = "https://pixeldrain.com/l/x"
    store.upsert_links(1, [link(url, "media")], ADAPTER_HOSTS)
    store.mark_probe(url, PROBE_UNKNOWN)
    row = get_link(store, url)
    assert (row.probe_status, row.probe_retries, row.dl_status) == \
        (PROBE_UNKNOWN, 1, DL_PENDING)
    store.mark_probe(url, PROBE_UNKNOWN)
    row = get_link(store, url)
    assert row.probe_retries == LINK_MAX_RETRY + 1
    assert row.dl_status == DL_EXHAUSTED
    assert "耗尽" in row.dl_note


def test_mark_probe_unregistered_url_raises(tmp_path):
  with make_store(tmp_path) as store:
    try:
      store.mark_probe("https://pixeldrain.com/l/none", PROBE_ALIVE)
      assert False, "应抛 ValueError"
    except ValueError:
      pass


# ---- mark_download ----

def test_mark_download_failed_exhausts_after_max_retry(tmp_path):
  with make_store(tmp_path) as store:
    url = "https://mega.nz/file/x"
    store.upsert_links(1, [link(url, "media")], ADAPTER_HOSTS)
    store.mark_probe(url, PROBE_ALIVE)
    store.mark_download(url, DL_FAILED, note="第一次失败")
    row = get_link(store, url)
    assert (row.dl_status, row.dl_retries) == (DL_FAILED, 1)
    store.mark_download(url, DL_FAILED, note="重试仍失败")
    row = get_link(store, url)
    assert row.dl_status == DL_EXHAUSTED and row.dl_retries == 2
    assert row.dl_note == "重试仍失败"


def test_mark_download_downloaded_records_artifacts(tmp_path):
  with make_store(tmp_path) as store:
    url = "https://mega.nz/file/x"
    store.upsert_links(1, [link(url, "media")], ADAPTER_HOSTS)
    store.mark_probe(url, PROBE_ALIVE)
    store.mark_download(url, DL_DOWNLOADED, path="m/x.zip", size=41424261,
                        note="整夹 ZIP")
    row = get_link(store, url)
    assert (row.dl_status, row.dl_path, row.dl_size, row.dl_note, row.dl_at) == \
        (DL_DOWNLOADED, "m/x.zip", 41424261, "整夹 ZIP", row.dl_at)
    assert row.dl_at


def test_mark_download_rejects_bad_status(tmp_path):
  with make_store(tmp_path) as store:
    url = "https://mega.nz/file/x"
    store.upsert_links(1, [link(url, "media")], ADAPTER_HOSTS)
    try:
      store.mark_download(url, "nope")
      assert False, "应抛 ValueError"
    except ValueError:
      pass


# ---- set_link_status：人工介入渠道 ----

def test_set_link_status_manual_to_downloaded(tmp_path):
  with make_store(tmp_path) as store:
    url = "https://workupload.com/file/x"
    store.upsert_links(1, [link(url, "media")], ADAPTER_HOSTS)
    assert get_link(store, url).dl_status == DL_MANUAL
    store.set_link_status(url, DL_DOWNLOADED, path="w/x.7z", size=1000,
                          note="人工浏览器下载")
    row = get_link(store, url)
    assert (row.dl_status, row.dl_path, row.dl_size, row.dl_note) == \
        (DL_DOWNLOADED, "w/x.7z", 1000, "人工浏览器下载")


def test_set_link_status_back_to_pending_resets_counters(tmp_path):
  with make_store(tmp_path) as store:
    # exhausted 由 download 失败耗尽 + probe 早已 unknown 的复合情形
    url = "https://pixeldrain.com/l/x"
    store.upsert_links(1, [link(url, "media")], ADAPTER_HOSTS)
    store.mark_probe(url, PROBE_UNKNOWN)
    store.mark_probe(url, PROBE_UNKNOWN)      # probe 耗尽 -> exhausted
    store.set_link_status(url, DL_PENDING)    # 人工决定重走
    row = get_link(store, url)
    assert (row.dl_status, row.dl_retries, row.probe_status, row.probe_retries) == \
        (DL_PENDING, 0, PROBE_PENDING, 0)
    assert url in [r.url for r in store.pending_probe_links()]
    # alive 证据保留：只有 dl 侧重置
    url2 = "https://pixeldrain.com/l/y"
    store.upsert_links(1, [link(url2, "media")], ADAPTER_HOSTS)
    store.mark_probe(url2, PROBE_ALIVE)
    store.mark_download(url2, DL_FAILED)
    store.mark_download(url2, DL_FAILED)      # dl 耗尽 -> exhausted
    store.set_link_status(url2, DL_PENDING)
    row2 = get_link(store, url2)
    assert (row2.dl_status, row2.dl_retries, row2.probe_status) == \
        (DL_PENDING, 0, PROBE_ALIVE)
    assert url2 in [r.url for r in store.pending_download_links()]


def test_set_link_status_rejects_bad_status(tmp_path):
  with make_store(tmp_path) as store:
    url = "https://pixeldrain.com/l/x"
    store.upsert_links(1, [link(url, "media")], ADAPTER_HOSTS)
    try:
      store.set_link_status(url, "whatever")
      assert False, "应抛 ValueError"
    except ValueError:
      pass


# ---- topic_consume_state ----

def test_topic_consume_state(tmp_path):
  with make_store(tmp_path) as store:
    # 无链接 topic：ready
    store.upsert_topics([TopicRef(topic_id=1, url="u1", title="t1")], now=1.0)
    store.save_parsed(1, [])
    assert store.topic_consume_state(1) == "ready"
    # 有链接但未登记：unregistered
    store.upsert_topics([TopicRef(topic_id=2, url="u2", title="t2")], now=1.0)
    store.save_parsed(2, [link("https://pixeldrain.com/l/a", "media")])
    assert store.topic_consume_state(2) == "unregistered"
    # 登记后：pending（还有在途）
    store.upsert_links(2, [link("https://pixeldrain.com/l/a", "media")], ADAPTER_HOSTS)
    assert store.topic_consume_state(2) == "pending"
    store.mark_probe("https://pixeldrain.com/l/a", PROBE_ALIVE)
    store.mark_download("https://pixeldrain.com/l/a", DL_DOWNLOADED)
    assert store.topic_consume_state(2) == "ready"
    # manual 也算终态：不卡 topic 消费闭环
    store.upsert_topics([TopicRef(topic_id=3, url="u3", title="t3")], now=1.0)
    store.save_parsed(3, [link("https://workupload.com/file/b", "media"),
                          link("https://iwara.tv/c", "source")])
    store.upsert_links(3, [link("https://workupload.com/file/b", "media"),
                           link("https://iwara.tv/c", "source")], ADAPTER_HOSTS)
    assert store.topic_consume_state(3) == "ready"


def test_topic_consume_state_missing_topic(tmp_path):
  with make_store(tmp_path) as store:
    try:
      store.topic_consume_state(999)
      assert False, "应抛 ValueError"
    except ValueError:
      pass


# ---- 汇总 ----

def test_link_status_counts(tmp_path):
  with make_store(tmp_path) as store:
    store.upsert_links(1, [
        link("https://pixeldrain.com/l/1", "media"),
        link("https://iwara.tv/2", "source"),
        link("https://workupload.com/file/3", "media"),
    ], ADAPTER_HOSTS)
    assert store.link_status_counts() == {DL_PENDING: 1, DL_SKIPPED: 1, DL_MANUAL: 1}


# ---- TopicStore 基础流转（补 eros store 单测缺口） ----

def test_topic_lifecycle_roundtrip(tmp_path):
  with make_store(tmp_path) as store:
    n_new, n_upd = store.upsert_topics(
        [TopicRef(topic_id=1, url="https://eros/t/1", title="t1",
                  bumped_at="2026-08-15T15:02:59.696Z")], now=100.0)
    assert (n_new, n_upd) == (1, 0)
    row = store.db.QueryOne(EroTopicItem, where="topic_id = ?", params=(1,))
    assert row.stat == int(Stat.DISCOVERED)
    assert row.bumped_at == "2026-08-15 15:02:59"   # 毫秒归一到秒

    store.mark_fetched(1)
    store.save_parsed(1, [link("https://pixeldrain.com/l/a", "media")])
    assert store.db.QueryOne(EroTopicItem, where="topic_id = ?", params=(1,)).stat \
        == int(Stat.PARSED)
    store.mark_consumed(1)
    assert store.db.QueryOne(EroTopicItem, where="topic_id = ?", params=(1,)).stat \
        == int(Stat.CONSUMED)

    # 更新帖（被顶起）重置回 DISCOVERED、清 links
    store.upsert_topics([], [TopicRef(topic_id=1, url="https://eros/t/1", title="t1v2",
                                      bumped_at="2026-08-20T00:00:00Z")], now=200.0)
    row = store.db.QueryOne(EroTopicItem, where="topic_id = ?", params=(1,))
    assert (row.stat, row.links_json, row.title) == (int(Stat.DISCOVERED), "", "t1v2")
    assert store.stat_counts() == {int(Stat.DISCOVERED): 1}
