
import asyncio

from scrape_all.sites.baidu_pan.save_plan import (
  build_save_plan, flat_to, format_plan, mirror_from,
)
from scrape_all.sites.baidu_pan.tree import stop_folder, walk_tree
from scrape_all.tests.fake_share import make_fake_lister


def full_tree():
  lister, _ = make_fake_lister()
  return asyncio.run(walk_tree(lister))


def test_select_files_by_level():
  tree = full_tree()
  ops = build_save_plan(
    tree,
    want=lambda n: not n.is_dir and n.name.endswith(".mp4"),
    target_for=mirror_from("/bangumi"),
  )

  assert len(ops) == 2
  assert ops[0].source_dir == "/Season 1"
  assert ops[0].names == ["01.mp4", "02.mp4"]
  assert ops[0].target_dir == "/bangumi/Season 1"
  assert ops[1].source_dir == "/Season 2"
  assert ops[1].names == ["21.mp4"]
  assert ops[1].target_dir == "/bangumi/Season 2"


def test_selected_folder_covers_subtree():
  # 选中 Season 1 整个文件夹后，它内部的 mp4 不再单独生成 op
  tree = full_tree()
  ops = build_save_plan(
    tree,
    want=lambda n: n.name == "Season 1" or n.name.endswith(".mp4"),
    target_for=mirror_from("/bangumi"),
  )

  assert len(ops) == 2
  root_ops = [o for o in ops if o.source_dir == "/"]
  assert len(root_ops) == 1
  assert root_ops[0].names == ["Season 1"]
  assert root_ops[0].target_dir == "/bangumi"     # 根级镜像就是 base 本身
  assert [o.source_dir for o in ops if o.source_dir != "/"] == ["/Season 2"]


def test_unexpanded_folder_selected_as_whole_unit():
  # 被 stop_folder 截断的文件夹（children=None）作为整体单元在父级勾选
  lister, _ = make_fake_lister()
  tree = asyncio.run(walk_tree(lister, policy=stop_folder("Season*")))
  ops = build_save_plan(
    tree,
    want=lambda n: n.name.startswith("Season"),
    target_for=flat_to("/all"),
  )

  assert len(ops) == 1
  assert ops[0].source_dir == "/"
  assert ops[0].names == ["Season 1", "Season 2"]
  assert ops[0].target_dir == "/all"


def test_flat_target():
  tree = full_tree()
  ops = build_save_plan(
    tree,
    want=lambda n: not n.is_dir and n.name.endswith(".mp4"),
    target_for=flat_to("/all"),
  )
  assert all(op.target_dir == "/all" for op in ops)


def test_selection_inside_unselected_folder_found():
  # 没选 Season 2，但选了它里面的 note.txt -> op 生成在 /Season 2/extra
  tree = full_tree()
  ops = build_save_plan(
    tree,
    want=lambda n: n.name == "note.txt",
    target_for=mirror_from("/bangumi"),
  )
  assert len(ops) == 1
  assert ops[0].source_dir == "/Season 2/extra"
  assert ops[0].names == ["note.txt"]
  assert ops[0].target_dir == "/bangumi/Season 2/extra"


def test_empty_plan():
  tree = full_tree()
  ops = build_save_plan(tree, want=lambda n: False, target_for=flat_to("/x"))
  assert ops == []
  assert format_plan(ops) == "(empty plan)"


def test_format_plan_output():
  tree = full_tree()
  ops = build_save_plan(
    tree,
    want=lambda n: n.name == "01.mp4",
    target_for=mirror_from("/bangumi"),
  )
  text = format_plan(ops)
  assert "[1]" in text and "/Season 1" in text and "+ 01.mp4" in text
