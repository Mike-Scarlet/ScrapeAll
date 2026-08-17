

# local_library 扫描：把 NAS 库根的现状解析进 LibraryStore。
# NAS 是事实源，本库只是可随时重建的镜像；工况外（解析不出月份的）不入库仅报告。

import os
import time
from collections import Counter
from typing import Optional

from scrape_all.local_library.parse import (
  Entry, classify_folder, parse_top_name,
)
from scrape_all.local_library.store import LibraryStore


def list_entries(path: str) -> list[Entry]:
  """列一层目录（目录项带 is_dir）；目录不可达抛 OSError 由调用方处理"""
  out = []
  for name in os.listdir(path):
    out.append(Entry(name, os.path.isdir(os.path.join(path, name))))
  return out


def scan(root: str, store: LibraryStore, uploader: str = "yejiang",
         yejiang_dir: str = "yejiang",
         now: Optional[float] = None) -> dict:
  """全量扫描库根：<root> 下 uploader 的顶层夹 + <root>/<yejiang_dir> 里已搬运的作者夹。

  返回报告 dict：{new, updated, by_method, out_of_scope, anomalies, warnings}
    - 根下的候选：文件夹名解析出 (creator, folder_date, uploader) 且 uploader 匹配；
      结构彻底可解析才入库，否则记 out_of_scope（带原因），留给人工处理
    - yejiang/ 下的作者夹：文件夹名即 creator（无日期），folder_date/original_name
      以库内值为准（DB 维护），只刷新月份/结构/last_seen
  """
  if now is None:
    now = time.time()
  report = {"new": 0, "updated": 0, "by_method": Counter(),
            "out_of_scope": [], "anomalies": [], "warnings": []}

  for name in sorted(os.listdir(root)):
    full = os.path.join(root, name)
    if not os.path.isdir(full):
      continue
    fn = parse_top_name(name)
    if fn is None or fn.uploader != uploader:
      continue
    folder_key = f"{uploader}:{fn.creator}"
    row = store.get(folder_key)
    if row is not None and row.rel_path != row.original_name:
      # 库里显示已搬运走，根目录却又出现同名源：先弄清再动，避免来回翻转
      report["anomalies"].append(
          f"{name}: 库记录已搬运（{row.rel_path}）但根目录又出现该源")
      continue
    sub = classify_folder(
        list_entries(full), lambda rel: list_entries(os.path.join(full, rel)))
    if not sub.ok:
      report["out_of_scope"].append((name, sub.reasons))
      continue
    state = store.upsert_folder(
        folder_key=folder_key, creator=fn.creator, uploader=uploader,
        original_name=name, rel_path=name, folder_date=fn.folder_date,
        parse_method=sub.parse_method, months=sub.months, now=now)
    report["new" if state == "new" else "updated"] += 1
    report["by_method"][sub.parse_method] += 1
    report["warnings"].extend(f"{name}: {w}" for w in sub.reasons)

  yj = os.path.join(root, yejiang_dir)
  if not os.path.isdir(yj):
    return report
  for name in sorted(os.listdir(yj)):
    full = os.path.join(yj, name)
    if not os.path.isdir(full):
      continue
    folder_key = f"{uploader}:{name}"
    row = store.get(folder_key)
    if row is None:
      report["anomalies"].append(f"{yejiang_dir}/{name}: 无库记录（先 scan 根目录再搬运？）")
      continue
    if parse_top_name(name) is not None:
      report["anomalies"].append(f"{yejiang_dir}/{name}: 搬进来了但仍是带日期命名")
      continue
    sub = classify_folder(
        list_entries(full), lambda rel: list_entries(os.path.join(full, rel)))
    if not sub.ok:
      # 已搬运的变工况外（人工动过结构）：保留库内旧值，只报告
      report["anomalies"].append(f"{yejiang_dir}/{name}: 重扫不再可解析 " + "; ".join(sub.reasons))
      continue
    state = store.upsert_folder(
        folder_key=folder_key, creator=row.creator, uploader=row.uploader,
        original_name=row.original_name, rel_path=f"{yejiang_dir}/{name}",
        folder_date=row.folder_date, parse_method=sub.parse_method,
        months=sub.months, now=now)
    report["new" if state == "new" else "updated"] += 1
    report["by_method"][sub.parse_method] += 1
    report["warnings"].extend(f"{yejiang_dir}/{name}: {w}" for w in sub.reasons)
  return report
