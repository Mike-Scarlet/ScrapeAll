
import asyncio

from scrape_all.sites.baidu_pan.tree import (
  WalkAction, chain, max_depth, skip, stop_folder, stop_below, stop_when_child, walk_tree, format_tree,
)
from scrape_all.tests.fake_share import FAKE_TREE, make_fake_lister


def run(coro):
  return asyncio.run(coro)


def find(root, path):
  """按路径取节点"""
  parts = [p for p in path.split("/") if p]
  node = root
  for p in parts:
    node = next(c for c in node.children if c.name == p)
  return node


def test_walk_no_policy_full_expansion():
  lister, calls = make_fake_lister()
  root = run(walk_tree(lister))

  assert root.path == "/" and root.depth == 0 and root.is_dir
  assert root.children is not None and len(root.children) == 3

  s1 = find(root, "/Season 1")
  assert s1.children is not None and len(s1.children) == 2
  assert find(root, "/Season 1/01.mp4").is_dir is False
  assert find(root, "/Season 1/01.mp4").size_text == "326.1M"
  assert find(root, "/Season 1/01.mp4").mtime_text == "2025-10-04 02:55"

  extra = find(root, "/Season 2/extra")
  assert extra.children is not None and len(extra.children) == 1

  empty = find(root, "/Season 2/empty")
  assert empty.children == []          # 展开过、空目录
  assert not empty.is_leaf_unit()

  assert sorted(calls) == sorted(FAKE_TREE.keys())


def test_walk_path_and_depth():
  lister, _ = make_fake_lister()
  root = run(walk_tree(lister))

  note = find(root, "/Season 2/extra/note.txt")
  assert note.path == "/Season 2/extra/note.txt"
  assert note.depth == 3


def test_max_depth_stops_expansion():
  lister, calls = make_fake_lister()
  root = run(walk_tree(lister, policy=max_depth(1)))

  s1 = find(root, "/Season 1")
  assert s1.children is None and s1.is_leaf_unit()   # depth 1 不再展开
  assert find(root, "/readme.txt").is_dir is False   # 文件不受影响
  # depth 1 的文件夹进入了"探测"但没列出内容
  assert "/" in calls and "/Season 1" not in calls


def test_stop_folder_saves_navigation():
  lister, calls = make_fake_lister()
  root = run(walk_tree(lister, policy=stop_folder("Season*")))

  assert find(root, "/Season 1").children is None
  assert find(root, "/Season 2").children is None
  assert find(root, "/readme.txt").is_dir is False
  # 进入前探测即 STOP：只列了根，省掉两次导航
  assert calls == ["/"]


def test_stop_when_child_stops_level():
  lister, calls = make_fake_lister()
  root = run(walk_tree(lister, policy=stop_when_child("extra*")))

  s2 = find(root, "/Season 2")
  assert s2.children is not None and len(s2.children) == 3  # 本层内容可见
  assert find(root, "/Season 2/extra").children is None      # 但不再进入子文件夹
  assert find(root, "/Season 2/21.mp4").is_dir is False
  assert "/Season 2/extra" not in calls
  assert "/Season 2/empty" not in calls


def test_skip_removes_folder_without_visiting():
  lister, calls = make_fake_lister()
  root = run(walk_tree(lister, policy=skip("extra")))

  s2 = find(root, "/Season 2")
  assert [c.name for c in s2.children] == ["21.mp4", "empty"]
  assert "/Season 2/extra" not in calls


def test_stop_below_expands_one_level():
  # stop_below("Season*")：Season 目录展开一级，其子文件夹（extra/empty）作为整体单元
  lister, calls = make_fake_lister()
  root = run(walk_tree(lister, policy=stop_below("Season*")))

  assert find(root, "/Season 1").children is not None       # 匹配目录本身被展开
  assert find(root, "/Season 2").children is not None
  assert find(root, "/Season 2/21.mp4").is_dir is False     # 展开层里的文件可见
  assert find(root, "/Season 2/extra").children is None     # 其子文件夹未展开
  assert "/Season 2/extra" not in calls                     # 进入前探测即停，没进 extra
  assert find(root, "/Season 2/empty").children is None


def test_stop_below_ignores_root_level():
  # 根下第一层的目录没有可匹配的父目录名，不受 stop_below 影响
  lister, calls = make_fake_lister()
  root = run(walk_tree(lister, policy=stop_below("Season*")))

  # "/Season 1" 的父是根，不会被 stop_below 停住；它下面的文件照常列出
  assert find(root, "/Season 1/01.mp4").is_dir is False
  assert "/Season 1" in calls


def test_chain_first_non_none_wins():
  lister, calls = make_fake_lister()
  root = run(walk_tree(lister, policy=chain(max_depth(5), skip("extra"))))

  assert [c.name for c in find(root, "/Season 2").children] == ["21.mp4", "empty"]
  assert find(root, "/Season 1/01.mp4").is_dir is False


def test_custom_function_policy():
  # 任意自定义函数也能当策略：本层一旦出现文件就停（不再进入子文件夹）
  def stop_when_files(ctx):
    if ctx.entries and any(not e.is_dir for e in ctx.entries):
      return WalkAction.STOP
    return None

  tree = {
    "/": [("A", True), ("B", True)],
    "/A": [("01.mp4", False)],
    "/B": [("C", True)],
    "/B/C": [("02.mp4", False)],
  }
  lister, calls = make_fake_lister(tree)
  root = run(walk_tree(lister, policy=stop_when_files))

  assert find(root, "/A").children is not None        # A 列出了 01.mp4
  assert find(root, "/A/01.mp4").is_dir is False
  assert find(root, "/B/C").children is not None      # B 没文件，继续下探
  assert find(root, "/B/C/02.mp4").is_dir is False


def test_format_tree_output():
  lister, _ = make_fake_lister()
  root = run(walk_tree(lister, policy=stop_folder("Season*")))
  text = format_tree(root)

  assert "Season 1" in text and "(未展开)" in text
  assert "readme.txt" in text and "1K" in text
