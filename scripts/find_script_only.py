# -*- coding: utf-8 -*-
"""盘点 eroscripts 库里"只有脚本、没有媒体"的帖子。

判定口径（三路取并集，任一命中即视为有媒体）：
  1. EroNorm 有 kind in (video, audio) 且 status=done
  2. EroLink 任意 kind 的链接 dl_status=downloaded 且 dl_path 是视频/音频扩展名
  3. EroExtract 解包产物里含视频/音频文件
脚本侧口径：EroLink kind=script 已下载，或 EroNorm 有 script/axis-script/variant-script。

用法：
  python scripts/find_script_only.py                 # 控制台输出 + 写 report
  python scripts/find_script_only.py --no-report     # 只看控制台
报告默认写到 data/script_only_report.txt
"""
import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'data' / 'eroscripts.db'
REPORT = ROOT / 'data' / 'script_only_report.txt'

MEDIA_EXT = (
    '.mp4', '.mkv', '.webm', '.avi', '.mov', '.wmv', '.m4v', '.mpg', '.mpeg', '.ts',
    '.wav', '.mp3', '.m4a', '.flac', '.ogg', '.opus',
)
SCRIPT_KINDS = ('script', 'axis-script', 'variant-script')


def is_media_path(p):
    return bool(p) and p.lower().endswith(MEDIA_EXT)


def extract_file_names(files_json):
    """从 EroExtract.files_json 里把所有字符串叶子都收上来当文件名候选。"""
    names = []

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            names.append(x)

    walk(files_json)
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-report', action='store_true', help='不写报告文件')
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    has_media, has_script = set(), set()
    reasons = defaultdict(list)

    for r in conn.execute(
            "select distinct topic_id from EroNorm where kind in ('video','audio') and status='done'"):
        has_media.add(r[0]); reasons[r[0]].append('EroNorm 媒体')

    for r in conn.execute("select first_topic_id, dl_path from EroLink where dl_status='downloaded'"):
        tid, path = r[0], r[1]
        if tid and is_media_path(path):
            has_media.add(tid); reasons[tid].append(f'下载落盘 {Path(path).name}')

    # EroLink 按 URL 全局去重，first_topic_id 只是首次消费者；同一 URL 会被多个帖引用。
    # 用每个帖自己的 links_json 对账 EroLink，避免归属误判（如 307860/307861 互引同两集）。
    dl_media = {}
    for r in conn.execute("select url, dl_path, dl_status from EroLink"):
        if r['dl_status'] == 'downloaded' and is_media_path(r['dl_path']):
            dl_media[r['url']] = Path(r['dl_path']).name
    for r in conn.execute("select topic_id, links_json from EroTopicItem where links_json is not null"):
        try:
            entries = json.loads(r['links_json'])
        except (ValueError, TypeError):
            continue
        for e in entries:
            hit = dl_media.get(e.get('url'))
            if hit and r[0]:
                has_media.add(r[0]); reasons[r[0]].append(f'links_json 命中已下载 {hit}')

    for r in conn.execute("select topic_id, files_json from EroExtract where status='done'"):
        tid, fj = r[0], r[1]
        if not tid or not fj:
            continue
        try:
            names = extract_file_names(json.loads(fj))
        except (ValueError, TypeError):
            continue
        hit = [n for n in names if n.lower().endswith(MEDIA_EXT)]
        if hit:
            has_media.add(tid); reasons[tid].append(f'压缩包内媒体 x{len(hit)}')

    for (tid,) in conn.execute(
            "select distinct first_topic_id from EroLink where kind='script' and dl_status='downloaded'"):
        if tid:
            has_script.add(tid)
    for (tid,) in conn.execute(
            "select distinct topic_id from EroNorm where kind in (%s) and status='done'"
            % ','.join('?' * len(SCRIPT_KINDS)), SCRIPT_KINDS):
        has_script.add(tid)

    missing = sorted(has_script - has_media)
    total = len(has_script)
    paired = len(has_script & has_media)

    lines = []
    add = lines.append
    add(f'eroscripts 帖子媒体盘点  db={DB.name}')
    add(f'有脚本帖: {total}   其中已有媒体: {paired}   只有脚本缺媒体: {len(missing)}')
    add('')

    for tid in missing:
        row = conn.execute(
            'select url, title, stat, links_json from EroTopicItem where topic_id=?', (tid,)).fetchone()
        if not row:
            continue
        add(f"[{tid}] {row['title']}")
        add(f"  {row['url']}")
        try:
            entries = [e for e in json.loads(row['links_json'] or '[]')
                       if e.get('kind') != 'script']
        except (ValueError, TypeError):
            entries = []
        if not entries:
            add('  (帖内除脚本外无任何链接)')
        for e in entries:
            l = conn.execute(
                'select kind, dl_status, dl_note, dl_path, first_topic_id from EroLink where url=?',
                (e.get('url'),)).fetchone()
            if l:
                tag = f"{l['kind']}:{l['dl_status']}"
                if l['first_topic_id'] and str(l['first_topic_id']) != str(tid):
                    tag += f"(归属帖 {l['first_topic_id']})"
                if l['dl_path']:
                    tag += f" -> {l['dl_path']}"
                note = f"  {l['dl_note']}" if l['dl_note'] else ''
            else:
                tag, note = '未入EroLink', ''
            add(f"  - {tag} {e.get('url')}{note}")
        add('')

    text = '\n'.join(lines)
    print(text)
    if not args.no_report:
        REPORT.write_text(text, encoding='utf-8')
        print(f'\n[report] {REPORT}', file=sys.stderr)
    conn.close()


if __name__ == '__main__':
    main()
