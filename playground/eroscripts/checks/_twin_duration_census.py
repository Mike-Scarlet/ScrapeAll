# -*- coding: utf-8 -*-
"""等时长双胞胎媒体簇普查（307860/307861 Kay 簇暴露的问题）。

背景：pairing 的 dur 层按 |Δ|<=2s 挑唯一，帖内/外池里若有两个以上媒体
时长互相在 2s 内，脚本就永远分不开 -> ambiguous/挂起；更隐蔽的是名字层
（exact/fuzzy）在双胞胎里挑中的那个可能按发帖出处（同 post 的 Video link）
看是配错了的，dur✓ 也救不回来（时长一样）。

本脚本扫全库（含 external_rels 外帖入池），列出所有"≥2 个媒体时长互在
±2s"的帖子和它们池里的媒体，以及该帖 EroNorm 配对/歧义/未配情况，
供人工核对配对正确性。

  python playground/eroscripts/checks/_twin_duration_census.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.sites.eroscripts.normalize import (DiskCachedProbe,
                                                   LibraryNormalizer)
from scrape_all.sites.eroscripts.pairing import VIDEO_EXTS, AUDIO_EXTS
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroNorm

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
DB = os.path.join(ROOT, 'data', 'eroscripts.db')
SRC = r'J:\es_scrape'
TOL = 2.0

probe = DiskCachedProbe(os.path.join(ROOT, 'data', 'eroscripts', '_norm_probe_cache.json'))

with TopicStore(DB) as store:
    nz = LibraryNormalizer(store, SRC, r'J:\es_norm', probe=probe)
    topics = nz.scan_topics()
    twin_topics = 0
    for tid in sorted(topics, key=int):
        t = topics[tid]
        ext = nz.external_rels(tid)
        media = [(r, nz._media_duration(r)) for r in
                 t['vid'] + sorted(x for x in ext
                                   if os.path.splitext(x)[1].lower() in VIDEO_EXTS)
                 + t['aud'] + sorted(x for x in ext
                                     if os.path.splitext(x)[1].lower() in AUDIO_EXTS)]
        media = [(r, d) for r, d in media if d is not None]
        if len(media) < 2:
            continue
        twins = []
        for i, (r1, d1) in enumerate(media):
            for r2, d2 in media[i + 1:]:
                if abs(d1 - d2) <= TOL:
                    twins.append((r1, r2, d1, d2))
        if not twins:
            continue
        twin_topics += 1
        norm = [(row.target_path, row.kind) for row in store.db.QueryRecords(
            EroNorm, where='topic_id = ?', params=(int(tid),))]
        print(f'[{tid}] 池内媒体 {len(media)} 个，等时长对:')
        for r1, r2, d1, d2 in twins:
            print(f'    {d1:8.3f}s  {os.path.basename(r1)}')
            print(f'    {d2:8.3f}s  {os.path.basename(r2)}')
        if norm:
            for tp, kind in norm:
                print(f'    EroNorm: {kind:6s} {tp}')
        else:
            print('    EroNorm: （无——脚本全歧义/未配，未进 es_norm）')
probe.save()
print(f'\n共 {twin_topics} 个帖存在等时长双胞胎媒体簇')
