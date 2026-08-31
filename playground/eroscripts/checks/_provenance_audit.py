# -*- coding: utf-8 -*-
"""provenance 对照审计：发帖出处 vs 已落库配对（只读，不动盘不动库）。

数据模型事实：EroLink 按 URL 全局去重、first_topic_id 只是首个登记帖、
下载落盘目录跟着 first_topic_id 走；每帖真实引用关系只在
EroTopicItem.links_json（含 post_number / section 出处）。

本审计把 links_json 的 post 级共现变成配对信号：
  STRONG —— script 条目 section='Script'（论坛模板区），且同 post 恰好
            一个已下载媒体文件 → 该脚本 ↔ 该媒体
  WEAK   —— 同 post 共现但脚本无模板区标记（如 post2 交叉引用）
  同一脚本 STRONG 候选冲突（>1 个不同媒体）→ 无信号

然后对照两件事：
  A. EroNorm done 组（同 stem 的 video+script source_path）：
       组对 ∈ STRONG → 确认；脚本有 STRONG 但指向别的媒体 → 矛盾（错配候选）
  B. 可救面：es_scrape 树里的脚本不在任何 EroNorm source 里、但 STRONG
     信号唯一给出媒体 → provenance 能自动消歧的（歧义/挂起/未配的子集）

  python playground/eroscripts/checks/_provenance_audit.py
报告写 data/eroscripts/provenance_audit.txt
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.sites.eroscripts.pairing import VIDEO_EXTS, AUDIO_EXTS
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink, EroNorm, EroTopicItem

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
DB = os.path.join(ROOT, 'data', 'eroscripts.db')
SRC = r'J:\es_scrape'
REPORT = os.path.join(ROOT, 'data', 'eroscripts', 'provenance_audit.txt')
MEDIA = VIDEO_EXTS | AUDIO_EXTS


def rel_of(path):
    return path.replace('\\', '/') if path else ''


def ext_of(rel):
    return os.path.splitext(rel)[1].lower()


with TopicStore(DB) as store:
    # url -> 已下载落盘文件 rel（只收文件型；gofile 目录型跳过）
    url2rel = {}
    for row in store.db.QueryRecords(EroLink, where="dl_status = 'downloaded'"):
        r = rel_of(row.dl_path)
        if r and ext_of(r) in MEDIA | {'.funscript', '.lua'}:
            url2rel[row.url] = r

    # ---- 每帖：post 级共现 -> 强/弱 provenance 候选 ----
    strong, weak = {}, {}          # script rel -> set(media rel)
    topics_rows = store.db.QueryRecords(EroTopicItem)
    for topic in topics_rows:
        try:
            entries = json.loads(topic.links_json or '[]')
        except (ValueError, TypeError):
            continue
        posts = defaultdict(lambda: {'scripts': [], 'media': []})
        for e in entries:
            r = url2rel.get(e.get('url') or '')
            if not r:
                continue
            if e.get('kind') == 'script' and ext_of(r) in {'.funscript', '.lua'}:
                posts[e.get('post_number')]['scripts'].append((r, e.get('section') or ''))
            elif e.get('kind') in ('media', 'source') and ext_of(r) in MEDIA:
                posts[e.get('post_number')]['media'].append(r)
        for pn, p in posts.items():
            if len(p['media']) != 1:
                continue
            m = p['media'][0]
            for s_rel, section in p['scripts']:
                tgt = strong if section.lower() == 'script' else weak
                tgt.setdefault(s_rel, set()).add(m)

    # 强信号内部冲突（同脚本多个不同媒体）-> 降级为无信号
    conflicted = {s for s, ms in strong.items() if len(ms) > 1}
    for s in conflicted:
        del strong[s]

    # ---- EroNorm done 组对照 ----
    norm_by_tid = defaultdict(list)
    for row in store.db.QueryRecords(EroNorm, where="status = 'done'"):
        norm_by_tid[int(row.topic_id)].append(row)

    confirms, contradic, no_signal = [], [], []
    for tid, rows in sorted(norm_by_tid.items()):
        media_rows = [r for r in rows if r.kind in ('video', 'audio')]
        script_rows = [r for r in rows if r.kind in ('script',)]
        stem2media = {os.path.splitext(os.path.basename(r.target_path))[0]: r
                      for r in media_rows}
        for sr in script_rows:
            stem = os.path.splitext(os.path.basename(sr.target_path))[0]
            mr = stem2media.get(stem)
            if mr is None:
                continue
            pair = (sr.source_path, mr.source_path)
            cand = strong.get(sr.source_path)
            if cand is None:
                no_signal.append(pair)
            elif pair[1] in cand:
                confirms.append(pair)
            else:
                contradic.append((tid, sr.source_path, mr.source_path,
                                  sorted(cand)))

    # ---- 可救面：树内脚本不在 EroNorm source、STRONG 唯一给媒体 ----
    in_norm = {r.source_path for rows in norm_by_tid.values() for r in rows}
    rescues = []
    for s_rel, ms in strong.items():
        if s_rel in in_norm or len(ms) != 1:
            continue
        rescues.append((s_rel, next(iter(ms))))

    lines = []
    add = lines.append
    add(f'provenance 对照审计（只读）')
    add(f'EroNorm done 组对照: 确认 {len(confirms)} / 矛盾 {len(contradic)} / '
        f'无出处信号 {len(no_signal)}')
    add(f'强信号冲突(同脚本指向多个媒体,已剔除): {len(conflicted)}')
    add(f'可救脚本(素材在库外、出处唯一给媒体): {len(rescues)}')
    add('')
    if contradic:
        add('==== 矛盾组（已落库配对与发帖出处不一致 —— 错配候选） ====')
        from scrape_all.sites.eroscripts.normalize import DiskCachedProbe
        probe = DiskCachedProbe(os.path.join(
            ROOT, 'data', 'eroscripts', '_norm_probe_cache.json'))
        for tid, s, v, want in contradic:
            add(f'[{tid}] 脚本 {s}')
            vi = probe(os.path.join(SRC, *v.split('/')))
            try:
                v_sz = os.path.getsize(os.path.join(SRC, *v.split('/')))
            except OSError:
                v_sz = -1
            add(f'    库内配: {v}  ({v_sz:,}B, '
                f'{(vi or {}).get("duration") or "?"}s)')
            for w in want:
                wi = probe(os.path.join(SRC, *w.split('/')))
                try:
                    w_sz = os.path.getsize(os.path.join(SRC, *w.split('/')))
                except OSError:
                    w_sz = -1
                vd, wd = ((vi or {}).get('duration'), (wi or {}).get('duration'))
                if v_sz == w_sz:
                    cls = '同体积镜像（无害）'
                elif vd is not None and wd is not None and abs(vd - wd) <= 2:
                    cls = '同时长不同体积（同内容不同档/封装，配哪个都对）'
                else:
                    cls = '★时长不同（真错配嫌疑，人工核）'
                add(f'    出处指: {w}  ({w_sz:,}B, {wd or "?"}s)  [{cls}]')
        probe.save()
        add('')
    if rescues:
        add('==== 可救脚本（provenance 唯一命中，重配即可进 es_norm） ====')
        for s, m in sorted(rescues):
            add(f'  {s}')
            add(f'    -> {m}')
        add('')
    if conflicted:
        add('==== 强信号冲突脚本（出处本身打架，仍需人工） ====')
        for s in sorted(conflicted):
            add(f'  {s}: {sorted(strong.get(s, weak.get(s, [])))}')
    text = '\n'.join(lines)
    print(text)
    with open(REPORT, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f'\n[report] {REPORT}', file=sys.stderr)
