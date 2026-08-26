import asyncio
import os

from scrape_all.downloader.adapters.base import DownloadResult, ProbeResult
from scrape_all.sites.eroscripts import consume
from scrape_all.sites.eroscripts.consume import (
    ABORT_AFTER, ConsumeAborted, finalize_sweep, process_topic, run_pass,
    select_topics, topic_links,
)
from scrape_all.sites.eroscripts.history import TopicRef
from scrape_all.sites.eroscripts.store import (
    DL_DEAD, DL_DOWNLOADED, DL_EXHAUSTED, DL_FAILED, DL_MANUAL, DL_PENDING,
    DL_SKIPPED, PROBE_ALIVE, PROBE_PENDING, PROBE_UNKNOWN, Stat, TopicStore,
)
from scrape_all.storage.models import EroLink, EroTopicItem

# 注册表真实 host（pixeldrain 有 adapter -> 登记即 pending；workupload 无 -> manual）
PD = "https://pixeldrain.com/l/{}"
WU = "https://workupload.com/file/{}"


class FakeAdapter:
  """可控 adapter：probe/download 各自可设返回形态或抛异常，计数调用"""

  def __init__(self, probe_status=PROBE_ALIVE, dl_status=DL_DOWNLOADED,
               size=100, filename="f.zip",
               raise_probe=False, raise_download=False):
    self.probe_status = probe_status
    self.dl_status = dl_status
    self.size = size
    self.filename = filename
    self.raise_probe = raise_probe
    self.raise_download = raise_download
    self.probe_calls = 0
    self.dl_calls = 0

  async def probe(self, engine, url):
    self.probe_calls += 1
    if self.raise_probe:
      raise RuntimeError("probe boom")
    return ProbeResult(status=self.probe_status, filename=self.filename,
                       size=self.size)

  async def download(self, engine, url, dest_dir):
    self.dl_calls += 1
    if self.raise_download:
      raise RuntimeError("download boom")
    return DownloadResult(status=self.dl_status,
                          path=os.path.join(dest_dir, self.filename),
                          size=self.size)


def fake_factory(mapping: dict):
  """url -> FakeAdapter 的注入工厂（未映射返回 None = 无 adapter）"""
  return lambda url: mapping.get(url)


def make_store(tmp_path):
  return TopicStore(str(tmp_path / "eros_consume_test.db"))


def get_link(store, url):
  return store.db.QueryOne(EroLink, where="url = ?", params=(url,))


def add_topic(store, topic_id, links, created="2026-05-01T00:00:00Z"):
  """links: [(url, kind)]，落成 stat=PARSED 帖"""
  store.upsert_topics([TopicRef(topic_id=topic_id, url=f"u{topic_id}",
                                title=f"t{topic_id}", created_at=created)], now=1.0)
  store.save_parsed(topic_id, [{"url": u, "kind": k, "name": "x", "section": "s",
                                "post_number": 1, "username": "u"} for u, k in links])


def topic_row(store, topic_id) -> EroTopicItem:
  return store.db.QueryOne(EroTopicItem, where="topic_id = ?", params=(topic_id,))


def quiet(_line=""):
  pass


# ---- select_topics / topic_links ----

def test_select_topics_since_ids_limit(tmp_path):
  with make_store(tmp_path) as store:
    add_topic(store, 1, [(PD.format(1), "media")], created="2026-03-31T00:00:00Z")
    add_topic(store, 2, [(PD.format(2), "media")], created="2026-04-01T00:00:00Z")
    add_topic(store, 3, [(PD.format(3), "media")], created="2026-04-05T00:00:00Z")
    add_topic(store, 4, [(PD.format(4), "media")], created="2026-04-09T00:00:00Z")
    # guard：含当日，前一天排除
    assert [t.topic_id for t in select_topics(store, since="2026-04-01")] == [2, 3, 4]
    # ids / limit 收窄
    assert [t.topic_id for t in select_topics(store, since="2026-04-01",
                                              ids=["3"])] == [3]
    assert [t.topic_id for t in select_topics(store, since="2026-04-01",
                                              limit=2)] == [2, 3]


def test_topic_links_filters_bad_entries(tmp_path):
  with make_store(tmp_path) as store:
    store.upsert_topics([TopicRef(topic_id=1, url="u", title="t")], now=1.0)
    store.save_parsed(1, [{"url": PD.format(1), "kind": "media"}, {"kind": "media"}])
    row = topic_row(store, 1)
    assert len(topic_links(row)) == 1   # 空 url 条目被滤
    row.links_json = "not json"
    assert topic_links(row) == []
    row.links_json = ""
    assert topic_links(row) == []


# ---- process_topic：登记 + 逐链接流水 ----

def test_execute_alive_downloads_and_consumes(tmp_path):
  with make_store(tmp_path) as store:
    url = PD.format("a")
    add_topic(store, 11, [(url, "media"), ("https://iwara.tv/v/1", "source")])
    a = FakeAdapter()
    res = asyncio.run(process_topic(store, topic_row(store, 11), r"J:\es",
                                    quiet, adapter_for_fn=fake_factory({url: a}),
                                    engine=object(), interlink_s=0))
    # 登记 2 条（iwara source -> skipped），链接只有 pixeldrain 走流水
    assert res["registered"] == 2 and res["skip"] == 1 and res["download"] == 1
    assert a.probe_calls == 1 and a.dl_calls == 1
    row = get_link(store, url)
    assert (row.probe_status, row.dl_status, row.dl_path, row.dl_size) == \
        (PROBE_ALIVE, DL_DOWNLOADED, os.path.join("11", "f.zip"), 100)
    assert res["consumed"] and topic_row(store, 11).stat == int(Stat.CONSUMED)


def test_execute_dead_never_downloads(tmp_path):
  with make_store(tmp_path) as store:
    url = PD.format("dead")
    add_topic(store, 11, [(url, "media")])
    a = FakeAdapter(probe_status="dead")
    res = asyncio.run(process_topic(store, topic_row(store, 11), r"J:\es",
                                    quiet, adapter_for_fn=fake_factory({url: a}),
                                    engine=object(), interlink_s=0))
    assert res["probe"] == 1 and a.dl_calls == 0
    assert get_link(store, url).dl_status == DL_DEAD
    assert res["consumed"]   # 死链也是终态，不卡帖


def test_final_links_skipped_zero_calls(tmp_path):
  with make_store(tmp_path) as store:
    url_dl, url_manual = PD.format("done"), WU.format("m")
    add_topic(store, 11, [(url_dl, "media"), (url_manual, "media")])
    a = FakeAdapter()
    # url_dl 登记后人工标记已下载；url_manual 登记即 manual（无 adapter host）
    store.upsert_links(11, topic_links(topic_row(store, 11)), frozenset())
    store.set_link_status(url_dl, DL_DOWNLOADED)
    res = asyncio.run(process_topic(store, topic_row(store, 11), r"J:\es",
                                    quiet, adapter_for_fn=fake_factory({url_dl: a}),
                                    engine=object(), interlink_s=0))
    assert res == {"registered": 0, "skip": 2, "todo": 0, "probe": 0,
                   "download": 0, "error": 0, "state": "ready", "consumed": True}
    assert a.probe_calls == 0 and a.dl_calls == 0


def test_no_adapter_defensive_path_sets_manual(tmp_path):
  with make_store(tmp_path) as store:
    url = PD.format("x")
    add_topic(store, 11, [(url, "media")])
    store.upsert_links(11, topic_links(topic_row(store, 11)),
                       frozenset({"pixeldrain.com"}))   # 登记时有 adapter
    # 处理时注册表收缩（工厂返回 None）-> 防御性转 manual
    res = asyncio.run(process_topic(store, topic_row(store, 11), r"J:\es",
                                    quiet, adapter_for_fn=fake_factory({}),
                                    engine=object(), interlink_s=0))
    assert res["skip"] == 1
    row = get_link(store, url)
    assert (row.dl_status, row.dl_note) == (DL_MANUAL, "无 adapter，人工处理")


def test_unknown_waits_next_pass_then_recovers(tmp_path):
  with make_store(tmp_path) as store:
    url = PD.format("slow")
    add_topic(store, 11, [(url, "media")])
    a = FakeAdapter(probe_status=PROBE_UNKNOWN)
    row11 = topic_row(store, 11)
    res = asyncio.run(process_topic(store, row11, r"J:\es", quiet,
                                    adapter_for_fn=fake_factory({url: a}),
                                    engine=object(), interlink_s=0))
    # pass1：unknown 不下载，帖留在 2
    assert res["probe"] == 1 and a.dl_calls == 0 and not res["consumed"]
    assert get_link(store, url).probe_retries == 1
    assert topic_row(store, 11).stat == int(Stat.PARSED)
    # pass2：页面渲染好了判活 -> 立刻下载收口
    a.probe_status = PROBE_ALIVE
    res = asyncio.run(process_topic(store, row11, r"J:\es", quiet,
                                    adapter_for_fn=fake_factory({url: a}),
                                    engine=object(), interlink_s=0))
    assert res["download"] == 1 and a.dl_calls == 1
    assert get_link(store, url).dl_status == DL_DOWNLOADED
    assert res["consumed"]


def test_download_failed_then_exhausted_across_passes(tmp_path):
  with make_store(tmp_path) as store:
    url = PD.format("flaky")
    add_topic(store, 11, [(url, "media")])
    a = FakeAdapter(raise_download=True)
    row11 = topic_row(store, 11)
    asyncio.run(process_topic(store, row11, r"J:\es", quiet,
                              adapter_for_fn=fake_factory({url: a}),
                              engine=object(), interlink_s=0))
    assert get_link(store, url).dl_status == DL_FAILED
    asyncio.run(process_topic(store, row11, r"J:\es", quiet,
                              adapter_for_fn=fake_factory({url: a}),
                              engine=object(), interlink_s=0))
    row = get_link(store, url)
    # 共 2 次尝试后耗尽（终态，不再进队）
    assert (row.dl_status, row.dl_retries) == (DL_EXHAUSTED, 2)
    res = asyncio.run(process_topic(store, row11, r"J:\es", quiet,
                                    adapter_for_fn=fake_factory({url: a}),
                                    engine=object(), interlink_s=0))
    # pass1 探活已判 alive（probe 只探 1 次），pass2 直落下载、耗尽后 pass3 全跳过
    assert res["skip"] == 1 and a.probe_calls == 1 and a.dl_calls == 2


def test_probe_exception_marks_unknown_counts_error(tmp_path):
  with make_store(tmp_path) as store:
    url = PD.format("boom")
    add_topic(store, 11, [(url, "media")])
    a = FakeAdapter(raise_probe=True)
    res = asyncio.run(process_topic(store, topic_row(store, 11), r"J:\es",
                                    quiet, adapter_for_fn=fake_factory({url: a}),
                                    engine=object(), interlink_s=0))
    assert res["error"] == 1
    row = get_link(store, url)
    assert (row.probe_status, row.probe_retries, row.dl_status) == \
        (PROBE_UNKNOWN, 1, DL_PENDING)


def test_consecutive_errors_abort_pass(tmp_path):
  with make_store(tmp_path) as store:
    urls = [(PD.format(i), "media") for i in range(ABORT_AFTER + 1)]
    add_topic(store, 11, urls)
    adapters = {u: FakeAdapter(raise_probe=True) for u, _ in urls}
    try:
      asyncio.run(process_topic(store, topic_row(store, 11), r"J:\es", quiet,
                                adapter_for_fn=fake_factory(adapters),
                                engine=object(), interlink_s=0))
      assert False, "应抛 ConsumeAborted"
    except ConsumeAborted:
      pass
    # 撤之前异常都落了库（unknown 计数在），帖留在 2
    statuses = [get_link(store, u).probe_status for u, _ in urls]
    assert statuses == [PROBE_UNKNOWN] * ABORT_AFTER + [PROBE_PENDING]
    assert topic_row(store, 11).stat == int(Stat.PARSED)


def test_dry_run_registers_but_touches_nothing(tmp_path):
  with make_store(tmp_path) as store:
    url = PD.format("d")
    add_topic(store, 11, [(url, "media")])
    a = FakeAdapter()
    res = asyncio.run(process_topic(store, topic_row(store, 11), r"J:\es",
                                    quiet, adapter_for_fn=fake_factory({url: a})))
    assert res["registered"] == 1 and res["todo"] == 1
    assert a.probe_calls == 0 and a.dl_calls == 0
    row = get_link(store, url)
    assert (row.probe_status, row.dl_status) == (PROBE_PENDING, DL_PENDING)
    assert not res["consumed"] and topic_row(store, 11).stat == int(Stat.PARSED)


def test_cross_topic_dedup_downloads_once(tmp_path):
  with make_store(tmp_path) as store:
    url = PD.format("shared")
    add_topic(store, 11, [(url, "media")], created="2026-04-02T00:00:00Z")
    add_topic(store, 22, [(url, "media")], created="2026-04-03T00:00:00Z")
    a = FakeAdapter()
    for tid in (11, 22):
      asyncio.run(process_topic(store, topic_row(store, tid), r"J:\es", quiet,
                                adapter_for_fn=fake_factory({url: a}),
                                engine=object(), interlink_s=0))
    assert a.dl_calls == 1                      # 第二帖直接跳过
    assert get_link(store, url).first_topic_id == 11   # 首见落最早帖
    assert topic_row(store, 22).stat == int(Stat.CONSUMED)


def test_dest_dir_uses_first_topic_id(tmp_path):
  with make_store(tmp_path) as store:
    url = PD.format("where")
    add_topic(store, 33, [(url, "media")], created="2026-04-02T00:00:00Z")
    add_topic(store, 11, [(url, "media")], created="2026-04-03T00:00:00Z")
    a = FakeAdapter()
    seen = {}
    factory = lambda u: (seen.setdefault(u, a)) if u == url else None
    asyncio.run(process_topic(store, topic_row(store, 33), r"J:\es", quiet,
                              adapter_for_fn=factory, engine=object(),
                              interlink_s=0))
    # 33 是首见帖（升序先处理），落盘目录/相对路径都归 33，即使 11 也在引用
    assert get_link(store, url).dl_path == os.path.join("33", "f.zip")


# ---- run_pass / finalize_sweep ----

def test_run_pass_totals(tmp_path):
  with make_store(tmp_path) as store:
    add_topic(store, 11, [(PD.format(1), "media"), ("https://iwara.tv/1", "source")])
    add_topic(store, 22, [(WU.format(2), "media")])   # 无 adapter host -> manual
    a1 = FakeAdapter()
    totals = asyncio.run(run_pass(store, [topic_row(store, 11),
                                          topic_row(store, 22)], r"J:\es", quiet,
                                  adapter_for_fn=fake_factory({PD.format(1): a1}),
                                  engine=object(), interlink_s=0))
    # skip=2：iwara source（登记即终态）+ workupload manual（登记即终态）
    assert totals == {"topics": 2, "registered": 3, "skip": 2, "todo": 0,
                      "probe": 0, "download": 1, "error": 0, "consumed": 2,
                      "aborted": False}
    assert store.link_status_counts() == {DL_DOWNLOADED: 1, DL_SKIPPED: 1,
                                          DL_MANUAL: 1}


class SlowAdapter(FakeAdapter):
  """probe 慢半拍并跟踪同时在飞的 worker 数，验证真并发"""

  def __init__(self, tracker, **kw):
    super().__init__(**kw)
    self.tracker = tracker

  async def probe(self, engine, url):
    self.tracker["active"] += 1
    self.tracker["max"] = max(self.tracker["max"], self.tracker["active"])
    await asyncio.sleep(0.05)
    self.tracker["active"] -= 1
    return await super().probe(engine, url)


def _add_numbered(store, tid, n, tag):
  add_topic(store, tid, [(PD.format(f"{tag}{i}"), "media") for i in range(n)])


def test_pool_actually_overlaps(tmp_path):
  with make_store(tmp_path) as store:
    _add_numbered(store, 11, 4, "s")
    tracker = {"active": 0, "max": 0}
    adapters = {PD.format(f"s{i}"): SlowAdapter(tracker) for i in range(4)}
    totals = asyncio.run(run_pass(store, [topic_row(store, 11)], r"J:\es",
                                  quiet, adapter_for_fn=fake_factory(adapters),
                                  engine=object(), interlink_s=0, concurrency=3))
    assert totals["download"] == 4 and totals["aborted"] is False
    assert tracker["max"] >= 2      # 真并发（串行恒为 1）
    # 串行对照
    tracker2 = {"active": 0, "max": 0}
    _add_numbered(store, 22, 3, "q")
    adapters2 = {PD.format(f"q{i}"): SlowAdapter(tracker2) for i in range(3)}
    asyncio.run(run_pass(store, [topic_row(store, 22)], r"J:\es", quiet,
                         adapter_for_fn=fake_factory(adapters2),
                         engine=object(), interlink_s=0, concurrency=1))
    assert tracker2["max"] == 1


def test_pool_dedup_url_across_topics_downloads_once(tmp_path):
  with make_store(tmp_path) as store:
    url = PD.format("shared")
    add_topic(store, 11, [(url, "media")], created="2026-04-02T00:00:00Z")
    add_topic(store, 22, [(url, "media")], created="2026-04-03T00:00:00Z")
    a = FakeAdapter()
    totals = asyncio.run(run_pass(store, [topic_row(store, 11),
                                          topic_row(store, 22)], r"J:\es",
                                  quiet, adapter_for_fn=fake_factory({url: a}),
                                  engine=object(), interlink_s=0, concurrency=3))
    assert a.dl_calls == 1                    # 队内去重，只下一次
    assert totals["download"] == 1 and totals["consumed"] == 2  # 两帖都收口
    assert store.link_status_counts() == {DL_DOWNLOADED: 1}


def test_pool_abort_on_error_streak(tmp_path):
  with make_store(tmp_path) as store:
    _add_numbered(store, 11, ABORT_AFTER + 3, "b")
    adapters = {PD.format(f"b{i}"): FakeAdapter(raise_probe=True)
                for i in range(ABORT_AFTER + 3)}
    totals = asyncio.run(run_pass(store, [topic_row(store, 11)], r"J:\es",
                                  quiet, adapter_for_fn=fake_factory(adapters),
                                  engine=object(), interlink_s=0, concurrency=2))
    assert totals["aborted"] is True
    rows = [get_link(store, PD.format(f"b{i}")) for i in range(ABORT_AFTER + 3)]
    unknown = sum(1 for r in rows if r.probe_status == PROBE_UNKNOWN)
    pending = sum(1 for r in rows if r.probe_status == PROBE_PENDING)
    # 撤队前异常都落库（unknown >= 阈值），队尾还有没吃到的
    assert unknown >= ABORT_AFTER and pending >= 1
    assert topic_row(store, 11).stat == int(Stat.PARSED)   # 不收口等重试


def test_finalize_sweep_consumes_ready_only(tmp_path):
  with make_store(tmp_path) as store:
    # 帖 11：链接人工处理完（manual 终态）-> ready 待扫尾
    add_topic(store, 11, [(WU.format(1), "media")])
    store.upsert_links(11, topic_links(topic_row(store, 11)), frozenset())
    # 帖 22：未登记（guard 外形态）-> 原地不动
    add_topic(store, 22, [(PD.format(2), "media")])
    # 帖 33：在途 -> pending
    add_topic(store, 33, [(PD.format(3), "media")])
    store.upsert_links(33, topic_links(topic_row(store, 33)),
                       frozenset({"pixeldrain.com"}))
    counts = finalize_sweep(store, quiet)
    assert counts == {"consumed": 1, "pending": 1, "unregistered": 1}
    assert topic_row(store, 11).stat == int(Stat.CONSUMED)
    assert topic_row(store, 22).stat == int(Stat.PARSED)
    assert topic_row(store, 33).stat == int(Stat.PARSED)
