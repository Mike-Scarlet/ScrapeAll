
from dataclasses import dataclass
from typing import Callable, List

from scrape_all.sites.baidu_pan.tree import PanNode

# 纯逻辑模块：树 + 选择规则 -> 转存操作序列，不依赖 playwright


@dataclass
class SaveOp:
  """一次"同级勾选 + 转存"操作（百度盘部分转存只支持同级选择）"""
  source_dir: str            # 分享内做勾选的目录路径，"/" 表示根
  names: List[str]           # 该级勾选的名字（文件，或整体转存的文件夹）
  target_dir: str            # 存到自己网盘的目标路径


Selection = Callable[[PanNode], bool]
"""want(node) -> 是否转存。选中文件夹 = 整棵子树一次带走"""

TargetFor = Callable[[str], str]
"""source_dir -> target_dir 的映射"""


def build_save_plan(root: PanNode, want: Selection, target_for: TargetFor) -> List[SaveOp]:
  """遍历树生成转存操作序列

  规则：
    - 每个有选中子项的目录生成一个 op（天然同级）
    - 选中文件夹后其子孙不再单独生成 op（整树由该文件夹带走）
    - children 为 None 的目录不会进入（其内部不可见，选它本身即可）
    - 根节点本身不可选（它就是整个分享）
  """
  ops: List[SaveOp] = []

  def rec(folder: PanNode):
    if folder.children is None:
      return
    picked_names = {c.name for c in folder.children if want(c)}
    if picked_names:
      ops.append(SaveOp(folder.path, sorted(picked_names), target_for(folder.path)))
    for c in folder.children:
      if c.is_dir and c.name not in picked_names:
        rec(c)

  rec(root)
  return ops


def mirror_from(base: str) -> TargetFor:
  """目标路径镜像源目录结构：source /A/B -> base/A/B；根 -> base"""
  def target(source_dir: str) -> str:
    if source_dir == "/":
      return base.rstrip("/")
    return base.rstrip("/") + source_dir
  return target


def flat_to(base: str) -> TargetFor:
  """所有操作都存到同一个目标目录"""
  def target(source_dir: str) -> str:
    return base
  return target


def format_plan(ops: List[SaveOp]) -> str:
  """计划的可读文本形式，执行前打印给人工核对（dry-run）

  每个条目同时给出最终落盘路径，来源与目标一目了然
  """
  if not ops:
    return "(empty plan)"
  lines: List[str] = []
  for i, op in enumerate(ops, 1):
    lines.append(f"[{i}] {op.source_dir}  ->  {op.target_dir}")
    for name in op.names:
      landing = op.target_dir.rstrip("/") + "/" + name
      lines.append(f"      + {name}  =>  {landing}")
  return "\n".join(lines)
