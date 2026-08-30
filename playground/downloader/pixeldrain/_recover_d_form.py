# /d 形态误判捞回（2026-08-29 修复配套）：
#   probe        复位 77 条 /d 形态误判 dead 的链接（probe/dl 双侧清零）并全量重探，
#                mark_probe 落库——活链翻 alive+dl pending，仍死的回 dead（新 note）
#   smoke --n 10 挑体积最小的前 N 条 alive 未下载链接，走 consume 同款
#                adapter.download + mark_download 真实落盘 J:\es_scrape\<topic_id>
# 用法：python playground/downloader/pixeldrain/_recover_d_form.py probe
#       python playground/downloader/pixeldrain/_recover_d_form.py smoke --n 10
import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from config import DOWNLOADER_PROXY_SERVER
from scrape_all.downloader.engine import DownloadEngine
from scrape_all.downloader.adapters import adapter_for
from scrape_all.sites.eroscripts.consume import fmt_size
from scrape_all.sites.eroscripts.store import (
    DL_PENDING, PROBE_DEAD, PROBE_PENDING, TopicStore,
)
from scrape_all.storage.models import EroLink

DEST_ROOT = r"J:\es_scrape"
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
DB = os.path.join(DB, "data", "eroscripts.db")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def form_of(url):
    m = re.match(r"^/(u|d|l|api/file|api/list)/", urlsplit(url).path)
    return m.group(1) if m else "?"


def select(store, probe_status=None, dl_status=None):
    rows = store.db.QueryRecords(EroLink, where="host = ?", params=["pixeldrain.com"])
    out = []
    for r in rows:
        if form_of(r.url) != "d":
            continue
        if probe_status and r.probe_status != probe_status:
            continue
        if dl_status and r.dl_status != dl_status:
            continue
        out.append(r)
    return out


def reset_for_reprobe(store, url):
    """probe/dl 双侧复位到自动流程入口（set_link_status 只复位 dl 侧且保留
    dead 探活证据，这里必须连 probe 侧一起清）"""
    item = EroLink(url=url)
    item.probe_status, item.probe_retries = PROBE_PENDING, 0
    item.dl_status, item.dl_retries = DL_PENDING, 0
    item.dl_note = "/d 形态修复复位，重探"
    store.db.RecordFieldChanged(
        item, ["probe_status", "probe_retries", "dl_status", "dl_retries", "dl_note"])
    store.db.Commit()


async def cmd_probe(store, engine):
    targets = select(store, probe_status="dead")
    others = select(store)  # 全部 /d 形态现状，供对账
    print(f"/d 形态共 {len(others)} 条，其中 probe=dead 待捞 {len(targets)} 条")
    if not targets:
        return
    adapter = adapter_for("https://pixeldrain.com/d/x")
    stat = Counter()
    total_size = 0
    for i, row in enumerate(targets, 1):
        reset_for_reprobe(store, row.url)
        try:
            p = await adapter.probe(engine, row.url)
            meta = {k: v for k, v in (("filename", p.filename), ("size", p.size))
                    if v} or None
            store.mark_probe(row.url, p.status, meta=meta, note=p.note)
        except Exception as e:
            note = f"{type(e).__name__}: {e}"
            store.mark_probe(row.url, "unknown", note=note)
            p = type("P", (), {"status": "unknown", "note": note, "size": None})()
        stat[p.status] += 1
        if p.status == "alive":
            total_size += (p.size or 0)
        print(f"  [{i:>2}/{len(targets)}] {p.status:7s} "
              f"{fmt_size(getattr(p, 'size', None))}  {row.url}")
        await asyncio.sleep(0.5)
    print(f"\n重探汇总: {dict(stat)}，alive 合计约 {fmt_size(total_size)}")


async def cmd_smoke(store, engine, n):
    rows = select(store, probe_status="alive", dl_status="pending")
    if not rows:
        print("没有 alive+pending 的 /d 链接（先跑 probe 子命令）")
        return

    def size_of(r):
        try:
            return json.loads(r.meta_json or "{}").get("size") or 10 ** 12
        except ValueError:
            return 10 ** 12

    rows.sort(key=size_of)
    picked = rows[:n]
    print(f"alive+pending 共 {len(rows)} 条，按体积最小取 {len(picked)} 条冒烟：")
    for r in picked:
        print(f"  {fmt_size(size_of(r))}  [{r.first_topic_id}] {r.url}")
    adapter = adapter_for("https://pixeldrain.com/d/x")
    stat = Counter()
    for i, row in enumerate(picked, 1):
        dest_dir = os.path.join(DEST_ROOT, str(row.first_topic_id))
        try:
            d = await adapter.download(engine, row.url, dest_dir)
        except Exception as e:
            note = f"{type(e).__name__}: {e}"
            store.mark_download(row.url, "failed", note=note)
            print(f"  [{i}/{len(picked)}] 异常转 failed: {note}")
            stat["error"] += 1
            continue
        rel = os.path.relpath(d.path, DEST_ROOT) if d.path else ""
        store.mark_download(row.url, d.status, path=rel, size=d.size, note=d.note)
        stat[d.status] += 1
        print(f"  [{i}/{len(picked)}] {d.status:10s} {fmt_size(d.size)}  "
              f"{rel or d.note or ''}")
        await asyncio.sleep(1)
    print(f"\n冒烟汇总: {dict(stat)}")


async def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe", help="复位 + 全量重探 /d 形态 dead 链接")
    p_smoke = sub.add_parser("smoke", help="真实下载体积最小的前 N 条")
    p_smoke.add_argument("--n", type=int, default=10)
    args = ap.parse_args()

    with TopicStore(DB) as store:
        async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
            if args.cmd == "probe":
                await cmd_probe(store, engine)
            else:
                await cmd_smoke(store, engine, args.n)


asyncio.run(main())
