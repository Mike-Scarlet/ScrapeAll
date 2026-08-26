

import os

from scrape_all.local_library.merge import (
  build_merge_plan, execute_merge, prune_empty_dirs,
)


def put(path, data: bytes):
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_bytes(data)


def make_sides(tmp_path):
  """[3] 侧三种作者 + 顶层散件；[4] 侧给 A 预置部分内容"""
  src = tmp_path / "extracted" / "[yejiang]"
  dst = tmp_path / "confirmed" / "[yejiang]"
  # A 合并作者（year_nested）：26.01 全新 / 25.01 同名同尺寸 / 25.02 同名异尺寸；
  # [4] 侧已有 2026/26.02 -> 2026 两边都在，走到下降递归分支
  put(src / "A" / "2025" / "25.01" / "a.mp4", b"same")
  put(src / "A" / "2025" / "25.02" / "b.mp4", b"diff-src")
  put(src / "A" / "2026" / "26.01" / "c.mp4", b"new")
  put(dst / "A" / "2025" / "25.01" / "a.mp4", b"same")
  put(dst / "A" / "2025" / "25.02" / "b.mp4", b"diff-dst!!")
  put(dst / "A" / "2026" / "26.02" / "d.mp4", b"old")
  # B 全新作者（month_flat 可解析）
  put(src / "B" / "25.03 x" / "x.mp4", b"b")
  # C 工况外：顶层系列目录
  (src / "C" / "单部" / "24.11 xx").mkdir(parents=True)
  put(src / "stray.txt", b"?")
  return str(src), str(dst)


def test_build_merge_plan_splits_in_and_out_of_scope(tmp_path):
  src, dst = make_sides(tmp_path)
  plans, report = build_merge_plan(src, dst)
  assert [p.creator for p in plans] == ["A", "B"]
  a, b = plans
  assert not a.is_new and a.parse_method == "year_nested"
  renames = [e for e in a.entries if e.kind == "rename"]
  sames = [e for e in a.entries if e.kind == "same"]
  assert [e.rel for e in renames] == ["2026/26.01"]
  assert [e.rel for e in sames] == ["2025/25.01/a.mp4"]
  assert len(a.conflicts) == 1 and "重名异尺寸" in a.conflicts[0]
  assert b.is_new and [e.rel for e in b.entries] == ["(整夹)"]
  assert [name for name, _ in report["out_of_scope"]] == ["C"]
  assert report["strays"] == ["stray.txt"]


def test_execute_merge_moves_and_is_idempotent(tmp_path):
  src, dst = make_sides(tmp_path)
  plans, _ = build_merge_plan(src, dst)
  result = execute_merge(plans)
  assert result["renamed"] == 2 and result["same"] == 1 and not result["failed"]
  assert os.path.isfile(os.path.join(dst, "A", "2026", "26.01", "c.mp4"))
  assert os.path.isdir(os.path.join(dst, "B", "25.03 x"))
  # same/冲突条目原地不动，留在 [3] 侧可见
  assert os.path.isfile(os.path.join(src, "A", "2025", "25.01", "a.mp4"))
  assert os.path.isfile(os.path.join(src, "A", "2025", "25.02", "b.mp4"))

  # 空目录收尾：A 的 2026 搬空后清掉壳，2025 有残留保留；
  # B 整夹一个 rename 直接消失（无壳可清，prune 空返回）
  assert not os.path.exists(os.path.join(src, "B"))
  assert prune_empty_dirs(os.path.join(src, "B")) == []
  assert prune_empty_dirs(os.path.join(src, "A"))
  assert not os.path.exists(os.path.join(src, "A", "2026"))
  assert os.path.isdir(os.path.join(src, "A", "2025", "25.02"))

  # 重跑：B 已消失不在清单；A 只剩 same/冲突，无 rename 可执行
  plans2, report2 = build_merge_plan(src, dst)
  assert [p.creator for p in plans2] == ["A"]
  assert not [e for p in plans2 for e in p.entries if e.kind == "rename"]
  result2 = execute_merge(plans2)
  assert result2["renamed"] == 0
  assert [name for name, _ in report2["out_of_scope"]] == ["C"]


def test_prune_only_removes_empty(tmp_path):
  root = tmp_path / "x"
  (root / "empty" / "deeper").mkdir(parents=True)
  (root / "full").mkdir()
  (root / "full" / "keep.txt").write_bytes(b"1")
  removed = prune_empty_dirs(str(root))
  assert not os.path.exists(root / "empty")
  assert os.path.isfile(root / "full" / "keep.txt")
  assert len(removed) == 2          # empty/deeper + empty
