"""bd_orchestrate_dryrun 纯逻辑自测：不碰浏览器，用假树验证策略/收集/对比/精确补齐。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrape_all.sites.baidu_pan.save_plan import build_save_plan, format_plan
from scrape_all.sites.baidu_pan.tree import EntryInfo, PanNode, walk_tree, format_tree
from playground.bd_orchestrate_dryrun import (
    POLICY, collect_creator_months, compute_targets,
    month_covered_names, name_covered, find_node, make_target_for)

# 假分享：year_nested + month_flat + 年份下散文件 三种结构混合
FAKE = {
    "/": [
        EntryInfo("Mimu", True), EntryInfo("AS109", True), EntryInfo("NFFA", True),
        EntryInfo("出现疑问请先看这里.txt", False),
    ],
    "/Mimu": [EntryInfo("2025", True), EntryInfo("2026", True), EntryInfo("保存资源自動領取優惠卷xx", True)],
    "/Mimu/2025": [EntryInfo("25.08", True), EntryInfo("25.09", True), EntryInfo("readme.txt", False)],
    "/Mimu/2026": [EntryInfo("26.01", True), EntryInfo("26.02 x", True), EntryInfo("特典", True)],
    "/AS109": [EntryInfo("2025-01", True), EntryInfo("2025.5.25【万由里 4】", True), EntryInfo("杂项", True)],
    "/NFFA": [EntryInfo("2025", True), EntryInfo("出现疑问请先看这里.txt", False)],
    "/NFFA/2025": [EntryInfo("25.01.mp4", False), EntryInfo("25.02.mp4", False),
                   EntryInfo("说明.md", False)],
}


async def lister(path):
    return FAKE.get(path, [])


async def main():
    tree = await walk_tree(lister, POLICY, root_name="全部文件")
    print(format_tree(tree))
    print()

    creators = collect_creator_months(tree)
    for name, info in creators.items():
        print(name, "->", {m: p for m, p in sorted(info["months"].items())}, "odd:", info["odd"])

    # 对比：Mimu 本地无记录；AS109 本地已有 2025.01、2025.05；NFFA 年份下散文件
    print()
    sel, d = compute_targets(set(creators["Mimu"]["months"]), None)
    print("Mimu 新作者:", sorted(sel), d["kind"])
    sel, d = compute_targets(set(creators["AS109"]["months"]), {"2025.01", "2025.05"})
    print("AS109 增量: 选中", sorted(sel), "| 重抓", d["resave"], "| 未覆盖", d["uncovered"],
          "| 跳过", d["skipped"], "| 本地独有", d["db_only"])
    sel, d = compute_targets(set(creators["NFFA"]["months"]), {"2025.01"})
    print("NFFA 散文件: 选中", sorted(sel), "| 重抓", d["resave"], "| 未覆盖", d["uncovered"])

    # ---- 重抓月精确补齐：名字覆盖集合 / 树节点查找
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
    print("month_covered_names ok:", sorted(covered))

    assert find_node(tree, "/") is tree
    node = find_node(tree, "/Mimu/2026/26.02 x")
    assert node is not None and node.is_leaf_unit()
    assert find_node(tree, "/不存在/路径") is None
    print("find_node ok")

    # ---- 模拟展开重抓月（expand_month_node 的就地变异），只挑缺失子项
    node.children = [
        PanNode("26.02 a.mp4", False, "/Mimu/2026/26.02 x/26.02 a.mp4", 4),
        PanNode("26.02 b", True, "/Mimu/2026/26.02 x/26.02 b", 4),
        PanNode("26.02 c.mp4", False, "/Mimu/2026/26.02 x/26.02 c.mp4", 4),
    ]
    cov = month_covered_names(["2026/26.02 x/26.02 a.mp4"])
    missing = [c for c in node.children if not name_covered(c.name, cov)]
    assert [c.name for c in missing] == ["26.02 b", "26.02 c.mp4"]
    ops = build_save_plan(tree, want=lambda n: n.path in {c.path for c in missing},
                          target_for=make_target_for({"Mimu": "/转存待定/[yejiang]/Mimu"}))
    assert len(ops) == 1 and ops[0].source_dir == "/Mimu/2026/26.02 x"
    assert ops[0].names == ["26.02 b", "26.02 c.mp4"]
    assert ops[0].target_dir == "/转存待定/[yejiang]/Mimu/2026/26.02 x"
    print("精确补齐计划 ok:")
    print(format_plan(ops))

    # ---- 目标映射：未匹配作者落 [yejiang] 约定，层级原样保留
    tgt = make_target_for({"AS109": "/转存待定/[yejiang]/AS109"})
    assert tgt("/AS109") == "/转存待定/[yejiang]/AS109"
    assert tgt("/AS109/2025-01") == "/转存待定/[yejiang]/AS109/2025-01"
    assert tgt("/NFFA/2025") == "/转存待定/[yejiang]/NFFA/2025"
    assert tgt("/") == "/转存待定"
    print("make_target_for ok")


asyncio.run(main())
