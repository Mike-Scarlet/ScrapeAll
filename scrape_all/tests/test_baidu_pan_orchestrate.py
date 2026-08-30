"""orchestrate 纯逻辑单测：不碰浏览器，用假树验证策略/收集/对比/精确补齐。

断言迁自 playground/baidu_pan/orchestrate/_logic_selftest.py（升包时随逻辑一起搬，原件已删见 git 历史），保持行为不漂移。
"""
import asyncio

from scrape_all.sites.baidu_pan.orchestrate import (
  collect_creator_months, collect_months_under, compute_targets, find_node,
  make_policy, make_target_for, month_covered_names, name_covered,
  resolve_local,
)
from scrape_all.sites.baidu_pan.save_plan import build_save_plan, format_plan
from scrape_all.sites.baidu_pan.tree import EntryInfo, PanNode, format_tree, walk_tree

TB = "/扒/20260801"   # 目标根固定值（正式入口按运行日期生成，这里只验证映射规则）

# 假分享：year_nested + month_flat + 年份下散文件 三种结构混合
FAKE = {
    "/": [
        EntryInfo("Mimu", True), EntryInfo("AS109", True), EntryInfo("NFFA", True),
        EntryInfo("出现疑问请先看这里.txt", False),
    ],
    "/Mimu": [EntryInfo("2025", True), EntryInfo("2026", True),
              EntryInfo("保存资源自動領取優惠卷xx", True)],
    "/Mimu/2025": [EntryInfo("25.08", True), EntryInfo("25.09", True),
                   EntryInfo("readme.txt", False)],
    "/Mimu/2026": [EntryInfo("26.01", True), EntryInfo("26.02 x", True),
                   EntryInfo("特典", True)],
    "/AS109": [EntryInfo("2025-01", True), EntryInfo("2025.5.25【万由里 4】", True),
               EntryInfo("杂项", True)],
    "/NFFA": [EntryInfo("2025", True), EntryInfo("出现疑问请先看这里.txt", False)],
    "/NFFA/2025": [EntryInfo("25.01.mp4", False), EntryInfo("25.02.mp4", False),
                   EntryInfo("说明.md", False)],
}


async def lister(path):
  return FAKE.get(path, [])


def walk(policy):
  return asyncio.run(walk_tree(lister, policy, root_name="全部文件"))


def test_full_walk_collect_and_targets():
  """local=None 全 walk（纯结构遍历）+ 月份收集 + 三种对比形态"""
  tree = walk(make_policy())
  assert format_tree(tree)  # 可读形式能生成

  creators = collect_creator_months(tree)
  assert set(creators) == {"Mimu", "AS109", "NFFA"}
  # Mimu：year_nested；广告目录被剔除；年份下的非月份目录进 odd
  assert creators["Mimu"]["months"] == {"2025.08": ["/Mimu/2025/25.08"],
                                        "2025.09": ["/Mimu/2025/25.09"],
                                        "2026.01": ["/Mimu/2026/26.01"],
                                        "2026.02": ["/Mimu/2026/26.02 x"]}
  assert creators["Mimu"]["odd"] == ["/Mimu/2026/特典"]
  # AS109：month_flat（2025-01 识别为 2025.01）；作者层直挂的非月份目录不算 odd
  assert set(creators["AS109"]["months"]) == {"2025.01", "2025.05"}
  assert creators["AS109"]["odd"] == []
  # NFFA：年份下带日期散文件也算月份（剥扩展名再试）
  assert set(creators["NFFA"]["months"]) == {"2025.01", "2025.02"}

  sel, d = compute_targets(set(creators["Mimu"]["months"]), None)
  assert d["kind"] == "新作者" and d["resave"] is None
  assert sel == set(creators["Mimu"]["months"])   # 新作者全选

  sel, d = compute_targets(set(creators["AS109"]["months"]), {"2025.01", "2025.05"})
  assert d["kind"] == "增量" and d["resave"] == "2025.05"
  assert sel == {"2025.05"} and d["uncovered"] == [] and d["skipped"] == ["2025.01"]

  sel, d = compute_targets({"2025.01", "2025.02"}, {"2025.01"})
  assert sel == {"2025.01", "2025.02"} and d["uncovered"] == ["2025.02"]


def test_empty_local_stops_at_creator_level():
  """空 local -> 所有作者都是"新作者"，停在作者层（整目录单元，不进年份层）"""
  tree = walk(make_policy(local={}))
  for name in ("Mimu", "AS109", "NFFA"):
    node = find_node(tree, f"/{name}")
    assert node is not None and node.is_leaf_unit(), name
  assert find_node(tree, "/Mimu/2025") is None          # 年份层没进去
  assert collect_months_under(find_node(tree, "/Mimu"))["months"] == {}


def test_mixed_local_walks_matched_creators_only():
  """混合 local：已匹配作者照常 walk 到月份层，未匹配停在作者层"""
  local = {"as109": ("AS109", "[yejiang]/AS109", {"2025.01", "2025.05"}, {})}
  tree = walk(make_policy(local=local))
  as109 = find_node(tree, "/AS109/2025-01")
  assert as109 is not None and as109.is_leaf_unit()
  assert find_node(tree, "/Mimu").is_leaf_unit()
  assert find_node(tree, "/NFFA").is_leaf_unit()


def test_plan_new_creator_root_op_and_matched_incremental():
  """新作者整目录 -> 根级 op；已匹配作者增量 -> 作者目录下 op"""
  local = {"as109": ("AS109", "[yejiang]/AS109", {"2025.01", "2025.05"}, {})}
  tree = walk(make_policy(local=local))
  selected = {"/Mimu", "/NFFA", "/AS109/2025.5.25【万由里 4】"}
  ops = build_save_plan(tree, want=lambda n: n.path in selected,
                        target_for=make_target_for({"AS109": f"{TB}/[yejiang]/AS109"}, TB))
  assert ops[0].source_dir == "/" and ops[0].names == ["Mimu", "NFFA"]
  assert ops[0].target_dir == f"{TB}/[yejiang]"      # 新作者整目录 -> [yejiang]/<名>
  assert ops[1].source_dir == "/AS109" and \
      ops[1].names == ["2025.5.25【万由里 4】"]
  assert ops[1].target_dir == f"{TB}/[yejiang]/AS109"
  assert format_plan(ops)


def test_month_covered_names_and_name_covered():
  covered = month_covered_names([
      "25.11 水兰儿 vip房⑪",                                   # 月目录自身
      "25.11 水兰儿 vip房⑪/25.11 水兰儿 vip房⑪.mp4",           # 月内文件（month_flat）
      "2024/24.01 普拉娜/23.10 普拉娜.mp4",                     # 月内文件（year_nested，含错位年份）
      "",
  ])
  assert "25.11 水兰儿 vip房⑪" in covered
  assert name_covered("25.11 水兰儿 vip房⑪ ", covered)          # 分享侧尾随空格
  assert name_covered("23.10 普拉娜.mp4", covered)
  assert not name_covered("25.11 新东西.mp4", covered)
  assert not name_covered("香風智乃 new.mp4", covered)           # 改名新版 -> 判缺失（要补）


def test_find_node():
  tree = walk(make_policy())
  assert find_node(tree, "/") is tree
  node = find_node(tree, "/Mimu/2026/26.02 x")
  assert node is not None and node.is_leaf_unit()
  assert find_node(tree, "/不存在/路径") is None


def test_precise_backfill_picks_missing_children():
  """模拟展开重抓月（expand_month_node 的就地变异），只挑缺失子项成 op"""
  tree = walk(make_policy())
  node = find_node(tree, "/Mimu/2026/26.02 x")
  node.children = [
      PanNode("26.02 a.mp4", False, "/Mimu/2026/26.02 x/26.02 a.mp4", 4),
      PanNode("26.02 b", True, "/Mimu/2026/26.02 x/26.02 b", 4),
      PanNode("26.02 c.mp4", False, "/Mimu/2026/26.02 x/26.02 c.mp4", 4),
  ]
  cov = month_covered_names(["2026/26.02 x/26.02 a.mp4"])
  missing = [c for c in node.children if not name_covered(c.name, cov)]
  assert [c.name for c in missing] == ["26.02 b", "26.02 c.mp4"]
  ops = build_save_plan(tree, want=lambda n: n.path in {c.path for c in missing},
                        target_for=make_target_for({"Mimu": f"{TB}/[yejiang]/Mimu"}, TB))
  assert len(ops) == 1 and ops[0].source_dir == "/Mimu/2026/26.02 x"
  assert ops[0].names == ["26.02 b", "26.02 c.mp4"]
  assert ops[0].target_dir == f"{TB}/[yejiang]/Mimu/2026/26.02 x"


def test_make_target_for_mapping():
  """已匹配镜像 rel_path；未登记作者兜底带名落 [yejiang]；根级 op 落 [yejiang]"""
  tgt = make_target_for({"AS109": f"{TB}/[yejiang]/AS109"}, TB)
  assert tgt("/AS109") == f"{TB}/[yejiang]/AS109"
  assert tgt("/AS109/2025-01") == f"{TB}/[yejiang]/AS109/2025-01"
  assert tgt("/NFFA/2025") == f"{TB}/[yejiang]/NFFA/2025"
  assert tgt("/") == f"{TB}/[yejiang]"


def test_resolve_local_matching_order():
  """目录名 casefold -> box_title -> 别名表"""
  local = {"as109": ("AS109", "[yejiang]/AS109", set(), {}),
           "リル": ("リル", "[yejiang]/リル", set(), {}),
           "はれ": ("はれ", "[yejiang]/はれ", set(), {})}
  db, how = resolve_local("AS109", "", local)
  assert db[0] == "AS109" and how == "目录名"
  db, how = resolve_local("随便什么", "AS109", local)
  assert db[0] == "AS109" and how.startswith("box_title")
  db, how = resolve_local("reel", "", local)
  assert db[0] == "リル" and how.startswith("别名表")
  db, how = resolve_local("harechippai", "合集", local)
  assert db[0] == "はれ" and how.startswith("别名表")
  assert resolve_local("陌生人", "", local) == (None, None)
