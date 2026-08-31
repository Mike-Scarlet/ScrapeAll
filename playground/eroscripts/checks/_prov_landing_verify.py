# -*- coding: utf-8 -*-
"""今日新落件盘上核验：直拷体积精确对上；转码探时长差/目标尺寸/h264。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.sites.eroscripts.normalize import DiskCachedProbe, media_info
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroNorm

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
DB = os.path.join(ROOT, 'data', 'eroscripts.db')
SRC = r'J:\es_scrape'
DST = r'J:\es_norm'

with TopicStore(DB) as store:
    probe = DiskCachedProbe(os.path.join(
        ROOT, 'data', 'eroscripts', '_norm_probe_cache.json'))
    rows = [r for r in store.db.QueryRecords(EroNorm)
            if (r.done_at or '').startswith('2026-08-31')]
    bad = 0
    for r in sorted(rows, key=lambda x: x.target_path):
        src_abs = os.path.join(SRC, *r.source_path.split('/'))
        dst_abs = os.path.join(DST, *r.target_path.split('/'))
        if not os.path.exists(dst_abs):
            print(f'[缺失] {r.target_path}')
            bad += 1
            continue
        if r.action == 'copy':
            ok = os.path.getsize(dst_abs) == os.path.getsize(src_abs)
            mark = 'OK' if ok else f'体积不符 {os.path.getsize(dst_abs)} vs {os.path.getsize(src_abs)}'
            if not ok:
                bad += 1
            print(f'[copy {mark}] {r.target_path}')
        else:   # transcode
            si, di = probe(src_abs), probe(dst_abs)
            w, h = di.get('width'), di.get('height')
            tw, th = (int(x) for x in r.action.split('=')[1].split(':'))
            import subprocess
            codec = ''
            try:
                j = subprocess.run(
                    [r'E:\Program Files\ffmpeg\bin\ffprobe.EXE', '-v', 'error',
                     '-print_format', 'json', '-show_streams', dst_abs],
                    capture_output=True, text=True, timeout=60)
                import json
                for st in json.loads(j.stdout).get('streams', []):
                    if st.get('codec_type') == 'video':
                        codec = st.get('codec_name', '')
            except Exception:
                codec = '?'
            dur_delta = (di.get('duration') or 0) - (si.get('duration') or 0)
            ok = (abs(dur_delta) <= 0.05 and (w, h) == (tw, th)
                  and codec == 'h264' and os.path.getsize(dst_abs) > 0)
            if not ok:
                bad += 1
            print(f'[transcode {"OK" if ok else "异常"} '
                  f'Δdur={dur_delta:+.2f}s {w}x{h}(要{tw}x{th}) {codec}] '
                  f'{r.target_path}')
    probe.save()
    print(f'\n核验 {len(rows)} 行，异常 {bad}')
