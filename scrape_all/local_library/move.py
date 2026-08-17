

# local_library 搬运：把根目录下"作者名 {YY.MM} [yejiang]"整夹搬进
# <root>/yejiang/<作者名>/（SMB 同卷 rename，服务端瞬移，不复制数据）。
# 永远先 build_plan + print_plan（dry-run），确认后才 execute_plan。

import json
import os
import time
from dataclasses import dataclass
from typing import Optional, Sequence

from scrape_all.local_library.store import LibraryStore
from scrape_all.storage.models import LibraryFolder


@dataclass
class MoveItem:
  """一条搬运计划：action=move 才会执行，skip 只展示原因"""
  folder_key: str
  creator: str
  src: str           # 绝对路径
  dst: str
  parse_method: str
  months_count: int
  action: str        # "move" / "skip"
  reason: str = ""   # skip 原因


def build_plan(root: str, yejiang_dir: str,
               folders: Sequence[LibraryFolder]) -> list[MoveItem]:
  """从库记录生成搬运计划（不碰文件系统以外的东西，只做存在性检查）"""
  yj = os.path.join(root, yejiang_dir)
  items = []
  for row in folders:
    if row.rel_path != row.original_name:
      items.append(MoveItem(row.folder_key, row.creator, "", "", row.parse_method,
                            len(_months(row)), "skip",
                            f"库记录不在根目录原位（rel_path={row.rel_path}）"))
      continue
    src = os.path.join(root, row.rel_path)
    dst = os.path.join(yj, row.creator)
    if os.path.exists(dst):
      items.append(MoveItem(row.folder_key, row.creator, src, dst, row.parse_method,
                            len(_months(row)), "skip", "目标已存在，不覆盖"))
    elif not os.path.isdir(src):
      items.append(MoveItem(row.folder_key, row.creator, src, dst, row.parse_method,
                            len(_months(row)), "skip", "源缺失（结构变了？重跑 scan）"))
    else:
      items.append(MoveItem(row.folder_key, row.creator, src, dst, row.parse_method,
                            len(_months(row)), "move"))
  return items


def print_plan(items: Sequence[MoveItem], root: str):
  moves = [i for i in items if i.action == "move"]
  skips = [i for i in items if i.action != "move"]
  print(f"库根: {root}")
  print(f"计划搬运 {len(moves)} 条，跳过 {len(skips)} 条")
  for i, it in enumerate(moves, 1):
    print(f"  [{i:02d}] move {os.path.basename(it.src)} -> {it.dst}"
          f"  ({it.parse_method}, {it.months_count} 个月份)")
  for it in skips:
    print(f"  skip {it.folder_key}: {it.reason}")


def execute_plan(items: Sequence[MoveItem], store: LibraryStore, yejiang_dir: str,
                 now: Optional[float] = None) -> dict:
  """执行 action=move 的条目。逐条 rename + 落库（可中断重跑，重跑时已搬的会
  在 build_plan 阶段变 skip），单条失败不影响其余。"""
  if now is None:
    now = time.time()
  result = {"moved": 0, "skipped": 0, "failed": []}
  todo = [i for i in items if i.action == "move"]
  if todo:
    os.makedirs(os.path.dirname(todo[0].dst), exist_ok=True)
  for it in todo:
    try:
      os.rename(it.src, it.dst)
      # 搬完立即校验 + 落库，任何一步炸掉都能靠重跑收敛
      if not os.path.isdir(it.dst) or os.path.exists(it.src):
        raise OSError(f"rename 后校验失败: {it.src} -> {it.dst}")
      store.update_rel_path(it.folder_key, f"{yejiang_dir}/{it.creator}", now=now)
      result["moved"] += 1
      print(f"  moved {it.creator}")
    except OSError as e:
      result["failed"].append(f"{it.creator}: {e}")
      print(f"  FAILED {it.creator}: {e}")
  result["skipped"] = len(items) - len(todo)
  return result


def _months(row: LibraryFolder) -> list[str]:
  try:
    return json.loads(row.content_json).get("downloaded_months", [])
  except (ValueError, AttributeError):
    return []
