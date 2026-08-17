"""bd_orchestrate_dryrun 纯逻辑自测：不碰浏览器，用假树验证策略/收集/对比。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrape_all.sites.baidu_pan.tree import EntryInfo, walk_tree, format_tree
from playground.bd_orchestrate_dryrun import (
    POLICY, collect_creator_months, compute_targets)

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


asyncio.run(main())
