
"""consume 阶段编排核心：stat=PARSED 帖子按 created_at 升序逐帖消费——
懒登记 EroLink + 逐链接 probe->download 同 phase 流水 + 全终态收口 CONSUMED。

单次 pass：选帖 ->（未登记则 upsert_links，零流量幂等）-> 逐链接（dl 终态
跳过；否则 probe 判活立刻 download）-> 帖内全终态则收口 stat 3。
单链接失败不卡整帖：unknown/failed 留在队里，下一次 pass 在重试窗口内
（LINK_MAX_RETRY，共 2 次尝试）再试，耗尽转 exhausted。

浏览器与 CLI 在 scripts/consume_links.py；本模块只依赖注入
engine / adapter_for_fn，全部逻辑可离线单测。
"""

import asyncio
import json
import os
from typing import Callable, Optional

from scrape_all.downloader.adapters import adapter_for, all_hosts
from scrape_all.storage.models import EroLink, EroTopicItem

from scrape_all.sites.eroscripts.store import (
    DL_FAILED, DL_FINAL, DL_MANUAL, PROBE_ALIVE, PROBE_PENDING, PROBE_UNKNOWN,
    TopicStore,
)

# 同一 pass 内连续异常到这个数就撤（多半浏览器/网络挂了，别把整批首试额度烧完）
ABORT_AFTER = 5


class ConsumeAborted(RuntimeError):
  pass


def fmt_size(n) -> str:
  return f"{n / 1024 / 1024:.1f}MB" if n and n >= 1024 * 1024 else f"{n}B" if n else "?"


def select_topics(store: TopicStore, since: Optional[str] = None,
                  ids=None, limit: Optional[int] = None) -> list[EroTopicItem]:
  """consume 候选帖：guard 内升序，再按 --ids / --limit 收窄"""
  rows = store.pending_consume_topics(since)
  if ids:
    want = {int(i) for i in ids}
    rows = [r for r in rows if r.topic_id in want]
  if limit:
    rows = rows[:limit]
  return rows


def topic_links(topic: EroTopicItem) -> list[dict]:
  """links_json -> [{url, kind, ...}]，坏 JSON / 空 url 容错过滤"""
  try:
    arr = json.loads(topic.links_json or "[]")
  except ValueError:
    arr = []
  return [l for l in arr if (l or {}).get("url")]


async def consume_link(store: TopicStore, engine, row: EroLink,
                       dest_root: str, adapter) -> tuple[str, str]:
  """单链接 probe->download 同 phase。返回 (kind, 人读结果)，kind：
  probe（判死/判墙/unknown，本轮不下载）/ download / error（异常已转 unknown|failed）。
  异常全部兜住落库（消耗重试额度），不向上抛。"""
  url = row.url
  if row.probe_status in (PROBE_PENDING, PROBE_UNKNOWN):
    try:
      p = await adapter.probe(engine, url)
    except Exception as e:
      note = f"{type(e).__name__}: {e}"
      store.mark_probe(url, PROBE_UNKNOWN, note=note)
      return "error", f"probe 异常转 unknown: {note}"
    meta = {k: v for k, v in (("filename", p.filename), ("size", p.size),
                              ("files", p.files)) if v}
    store.mark_probe(url, p.status, meta=meta or None, note=p.note)
    if p.status != PROBE_ALIVE:
      line = f"probe={p.status} {p.filename or ''}".rstrip()
      return "probe", f"{line} {p.note}".rstrip()
  # probe 刚判活，或早已 alive（dl failed 的重试路径）
  dest_dir = os.path.join(dest_root, str(row.first_topic_id))
  try:
    d = await adapter.download(engine, url, dest_dir)
  except Exception as e:
    note = f"{type(e).__name__}: {e}"
    store.mark_download(url, DL_FAILED, note=note)
    return "error", f"download 异常转 failed: {note}"
  rel = os.path.relpath(d.path, dest_root) if d.path else ""
  store.mark_download(url, d.status, path=rel, size=d.size, note=d.note)
  line = f"download={d.status} {fmt_size(d.size)}"
  return "download", f"{line} {d.note or ''}".rstrip()


async def process_topic(store: TopicStore, topic: EroTopicItem, dest_root: str,
                        emit: Callable[[str], None], adapter_for_fn=adapter_for,
                        engine=None, interlink_s: float = 1.0) -> dict:
  """消费单帖。engine=None 即 dry-run：懒登记照做（零流量幂等），链接不动、
  stat 不动，非终态链接计 todo 供报数。返回计数 dict。"""
  links = topic_links(topic)
  registered = 0
  if store.topic_consume_state(topic.topic_id) == "unregistered":
    registered = store.upsert_links(topic.topic_id, links, all_hosts())
    emit(f"  登记链接：新建 {registered} / 复用 {len(links) - registered}")
  counts = {"skip": 0, "todo": 0, "probe": 0, "download": 0, "error": 0}
  consecutive_errors = 0
  for l in links:
    url = l["url"]
    row = store.db.QueryOne(EroLink, where="url = ?", params=(url,))
    if row is None:
      continue
    if row.dl_status in DL_FINAL:
      counts["skip"] += 1
      continue
    adapter = adapter_for_fn(url)
    if adapter is None:
      store.set_link_status(url, DL_MANUAL, note="无 adapter，人工处理")
      counts["skip"] += 1
      emit(f"  {url}\n    无 adapter -> manual")
      continue
    if engine is None:
      emit(f"  [dry] {url}  待 probe+download")
      counts["todo"] += 1
      continue
    kind, outcome = await consume_link(store, engine, row, dest_root, adapter)
    emit(f"  {url}\n    {outcome}")
    counts[kind] += 1
    if kind == "error":
      consecutive_errors += 1
      if consecutive_errors >= ABORT_AFTER:
        raise ConsumeAborted(
            f"连续 {ABORT_AFTER} 条链接异常（疑似浏览器/网络挂了），本 pass 提前撤；"
            f"已完成的不受影响")
    else:
      consecutive_errors = 0
    if interlink_s:
      await asyncio.sleep(interlink_s)
  state = store.topic_consume_state(topic.topic_id)
  consumed = False
  if state == "ready" and engine is not None:
    store.mark_consumed(topic.topic_id)
    consumed = True
  return {"registered": registered, **counts, "state": state, "consumed": consumed}


async def run_pass(store: TopicStore, topics: list[EroTopicItem], dest_root: str,
                   emit: Callable[[str], None], adapter_for_fn=adapter_for,
                   engine=None, interlink_s: float = 1.0,
                   concurrency: int = 1) -> dict:
  """一批帖子的流水汇总（execute 与 dry-run 共用；engine=None 即 dry-run）。
  并发模型：先顺序展平（懒登记 + url 去重进队，队序=帖升序首见序），再
  concurrency 个 worker 并发消费队列，最后统一扫尾——选中帖里链接全终态的
  逐个收口（manual/死链不卡帖，unknown/failed 留 2 等下一 pass）。
  跨 worker 连续 ABORT_AFTER 条异常置 stop 撤 pass（totals['aborted']=True），
  已完成的不受影响。"""
  totals = {"topics": len(topics), "registered": 0, "skip": 0, "todo": 0,
            "probe": 0, "download": 0, "error": 0, "consumed": 0,
            "aborted": False}
  # -- 展平：懒登记 + url -> 引用帖收集（跨帖重复 URL 只进队一次）--
  url_topics: dict[str, list[int]] = {}
  for topic in topics:
    links = topic_links(topic)
    if store.topic_consume_state(topic.topic_id) == "unregistered":
      n = store.upsert_links(topic.topic_id, links, all_hosts())
      totals["registered"] += n
      emit(f"=== topic {topic.topic_id}  {topic.created_at}  {topic.title[:48]}"
           f"  登记链接：新建 {n} / 复用 {len(links) - n}")
    else:
      emit(f"=== topic {topic.topic_id}  {topic.created_at}  {topic.title[:48]}")
    for l in links:
      tids = url_topics.setdefault(l["url"], [])
      if topic.topic_id not in tids:
        tids.append(topic.topic_id)
  queue: list[str] = []
  for url, tids in url_topics.items():
    row = store.db.QueryOne(EroLink, where="url = ?", params=(url,))
    if row is None or row.dl_status in DL_FINAL:
      totals["skip"] += 1
      continue
    if engine is None:
      emit(f"  [dry] {url}  待 probe+download")
      totals["todo"] += 1
    else:
      queue.append(url)
  # -- worker 池 --
  if queue:
    work = asyncio.Queue()
    for u in queue:
      work.put_nowait(u)
    stop = asyncio.Event()
    err_streak = 0

    async def worker():
      nonlocal err_streak
      while not stop.is_set():
        try:
          url = work.get_nowait()
        except asyncio.QueueEmpty:
          return
        row = store.db.QueryOne(EroLink, where="url = ?", params=(url,))
        if row is None or row.dl_status in DL_FINAL:
          totals["skip"] += 1
          continue
        adapter = adapter_for_fn(url)
        if adapter is None:
          store.set_link_status(url, DL_MANUAL, note="无 adapter，人工处理")
          totals["skip"] += 1
          emit(f"  {url}\n    无 adapter -> manual")
          continue
        kind, outcome = await consume_link(store, engine, row, dest_root, adapter)
        totals[kind] += 1
        emit(f"  [{row.first_topic_id}] {url}\n    {outcome}")
        if kind == "error":
          err_streak += 1
          if err_streak >= ABORT_AFTER:
            stop.set()
        else:
          err_streak = 0
        if interlink_s:
          await asyncio.sleep(interlink_s)

    n_workers = max(1, min(concurrency, len(queue)))
    await asyncio.gather(*(worker() for _ in range(n_workers)))
    totals["aborted"] = stop.is_set()
  # -- 扫尾收口：选中帖里链接全终态的推 3 --
  for topic in topics:
    if store.topic_consume_state(topic.topic_id) == "ready":
      store.mark_consumed(topic.topic_id)
      totals["consumed"] += 1
      emit(f"topic {topic.topic_id} -> CONSUMED（全终态）")
  return totals


def finalize_sweep(store: TopicStore, emit: Callable[[str], None]) -> dict:
  """零流量扫尾：把链接全终态的 stat=PARSED 帖推到 CONSUMED。
  人工 set 处理完 manual 清单后跑这个收口；unregistered（guard 外未登记）
  原地不动。返回 {consumed, pending, unregistered}。"""
  counts = {"consumed": 0, "pending": 0, "unregistered": 0}
  for topic in store.pending_consume_topics():
    state = store.topic_consume_state(topic.topic_id)
    if state == "ready":
      store.mark_consumed(topic.topic_id)
      counts["consumed"] += 1
      emit(f"topic {topic.topic_id} -> CONSUMED")
    else:
      counts[state] += 1
  return counts
