

# local_library 合并：[3]extracted/<yejiang>/<作者>/ 下载解压产物并入
# [4]confirmed/<yejiang>/<作者>/ 正式库（SMB 同卷 rename，服务端瞬移）。
# 算法只碰"结构完全可解析"（classify ok）的作者夹；工况外的原地留给人工，
# 人工处理完跑 scan 统一定状态。永远先 build_merge_plan + print_plan（dry-run），
# 确认后才 execute_merge（幂等：重跑时已并的条目自然变 same/空）。

import os
from dataclasses import dataclass, field

from scrape_all.local_library.parse import classify_folder
from scrape_all.local_library.scan import list_entries


@dataclass
class MergeEntry:
    """一条搬移动作：rename=同卷移动（src 在目标侧不存在）；same=无需动作"""
    src: str            # 绝对路径
    dst: str
    kind: str           # "rename" / "same"
    rel: str            # 作者夹内相对路径（报告用）


@dataclass
class CreatorPlan:
    """一个作者夹的合并计划（action 只会是 merge，工况外/散件不生成 plan）"""
    creator: str
    is_new: bool                      # [4] 侧无同名作者夹：整夹一次 rename
    parse_method: str
    entries: list[MergeEntry] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)   # 重名异尺寸/文件夹撞文件


def _merge_tree(src: str, dst: str, rel_base: str,
                entries: list[MergeEntry], conflicts: list[str]):
    """递归对比两棵现成的目录树，收集搬移动作（不动文件系统）。

    目标侧不存在 -> 整项 rename（目录整树一次带走）；两侧同是目录 -> 下降；
    两侧同是文件 -> 同尺寸视为已并（same），异尺寸记冲突；目录撞文件记冲突。
    """
    for name in sorted(os.listdir(src)):
        s, d = os.path.join(src, name), os.path.join(dst, name)
        rel = f"{rel_base}/{name}" if rel_base else name
        if not os.path.exists(d):
            entries.append(MergeEntry(s, d, "rename", rel))
        elif os.path.isdir(s) and os.path.isdir(d):
            _merge_tree(s, d, rel, entries, conflicts)
        elif not os.path.isdir(s) and not os.path.isdir(d):
            if os.path.getsize(s) == os.path.getsize(d):
                entries.append(MergeEntry(s, d, "same", rel))
            else:
                conflicts.append(
                    f"{rel}: 重名异尺寸 [3]={os.path.getsize(s)}B [4]={os.path.getsize(d)}B")
        else:
            kind_s = "目录" if os.path.isdir(s) else "文件"
            kind_d = "目录" if os.path.isdir(d) else "文件"
            conflicts.append(f"{rel}: [3]是{kind_s} [4]是{kind_d}，同名相撞")


def build_merge_plan(src_root: str, dst_root: str) -> tuple[list[CreatorPlan], dict]:
    """遍历 [3] 侧作者夹生成合并计划。

    返回 (plans, report)：
      plans   仅工况内作者，按作者名排序
      report  {"out_of_scope": [(作者, 原因)], "strays": 顶层非目录条目}
              工况外与散件一律原地不动，留给人工。
    """
    report = {"out_of_scope": [], "strays": []}
    plans: list[CreatorPlan] = []
    for name in sorted(os.listdir(src_root)):
        src = os.path.join(src_root, name)
        if not os.path.isdir(src):
            report["strays"].append(name)
            continue
        sub = classify_folder(
            list_entries(src), lambda rel: list_entries(os.path.join(src, rel)))
        if not sub.ok:
            report["out_of_scope"].append((name, "; ".join(sub.reasons[:2])))
            continue
        dst = os.path.join(dst_root, name)
        plan = CreatorPlan(name, not os.path.isdir(dst), sub.parse_method)
        if plan.is_new:
            # 全新作者：目标作者夹不存在，整夹一个 rename 搞定
            plan.entries.append(MergeEntry(src, dst, "rename", "(整夹)"))
        else:
            _merge_tree(src, dst, "", plan.entries, plan.conflicts)
        plans.append(plan)
    return plans, report


def print_plan(plans: list[CreatorPlan], report: dict, src_root: str, dst_root: str):
    merges = [p for p in plans if any(e.kind == "rename" for e in p.entries)]
    renames = sum(1 for p in plans for e in p.entries if e.kind == "rename")
    same = sum(1 for p in plans for e in p.entries if e.kind == "same")
    conflicts = sum(len(p.conflicts) for p in plans)
    print(f"源: {src_root}")
    print(f"目标: {dst_root}")
    print(f"工况内作者 {len(plans)}（全新 {sum(1 for p in plans if p.is_new)} / "
          f"合并 {sum(1 for p in plans if not p.is_new)}）："
          f"搬移 {renames} 项，重名同尺寸跳过 {same}，冲突 {conflicts}")
    for i, p in enumerate(plans, 1):
        n_rename = sum(1 for e in p.entries if e.kind == "rename")
        n_same = len(p.entries) - n_rename
        mark = "全新" if p.is_new else "合并"
        print(f"  [{i:02d}] {p.creator} ({p.parse_method}) {mark} "
              f"搬移{n_rename} 同尺寸{n_same} 冲突{len(p.conflicts)}")
        for c in p.conflicts[:5]:
            print(f"      !! {c}")
    if report["out_of_scope"]:
        print(f"\n工况外（原地不动，留人工）: {len(report['out_of_scope'])}")
        for name, reason in report["out_of_scope"]:
            print(f"  ? {name}: {reason}")
    if report["strays"]:
        print(f"\n顶层散件（不是文件夹，留人工）: {report['strays']}")
    if not merges:
        print("\n没有待搬移的条目（全部已并或全部工况外）")
    return len(merges), conflicts


def execute_merge(plans: list[CreatorPlan]) -> dict:
    """执行全部 rename 条目。单条失败不中断其余，返回结果供汇总；幂等可重跑。

    空目录壳的收尾不在这一步（renames 里有计划的 src 作者夹路径才能定位），
    由调用方对每个工况内作者夹调用 prune_empty_dirs。
    """
    result = {"renamed": 0, "same": 0, "failed": []}
    for p in plans:
        for e in p.entries:
            if e.kind != "rename":
                result["same"] += 1
                continue
            try:
                os.rename(e.src, e.dst)
                if os.path.exists(e.src) or not os.path.exists(e.dst):
                    raise OSError(f"rename 后校验失败: {e.rel}")
                result["renamed"] += 1
            except OSError as err:
                result["failed"].append(f"{p.creator}/{e.rel}: {err}")
                print(f"  FAILED {p.creator}/{e.rel}: {err}")
    return result


def prune_empty_dirs(creator_src: str) -> list[str]:
    """自底向上删空目录（只删得动空的），返回删掉的路径列表。

    作者夹本体空了也会一并消失——[3] 侧剩下的就只剩工况外与有残留的。
    """
    removed = []
    if not os.path.isdir(creator_src):
        return removed
    for dirpath, _dirnames, _files in os.walk(creator_src, topdown=False):
        try:
            os.rmdir(dirpath)
            removed.append(dirpath)
        except OSError:
            pass              # 非空（残留/失败条目），保留
    return removed
