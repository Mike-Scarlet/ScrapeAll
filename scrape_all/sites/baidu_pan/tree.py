
import fnmatch
from dataclasses import dataclass
from enum import Enum, auto
from typing import Awaitable, Callable, List, Optional

# 纯逻辑模块：不依赖 playwright，用假 lister 即可单测（见 tests/）


@dataclass
class EntryInfo:
  """lister 返回的单条列表项（对应页面上的一行）"""
  name: str
  is_dir: bool
  size_text: Optional[str] = None    # 页面显示原文，如 "326.1M" / "-"
  mtime_text: Optional[str] = None   # 页面显示原文，如 "2025-10-04 02:55"


@dataclass
class PanNode:
  """分享目录树节点

  children 三态（部分转存的关键约定）:
    None = 未展开（被策略截断，或父级未进入）→ 转存时作为整体单元
    []   = 展开过、空目录
    list = 展开过，内容为直接子节点
  文件节点的 children 恒为 None
  """
  name: str
  is_dir: bool
  path: str          # 相对分享根，"/" 开头；根节点本身为 "/"
  depth: int         # 根为 0
  size_text: Optional[str] = None
  mtime_text: Optional[str] = None
  children: Optional[List["PanNode"]] = None

  def is_leaf_unit(self) -> bool:
    """是否为整体转存单元（未展开的文件夹）"""
    return self.is_dir and self.children is None


class WalkAction(Enum):
  DESCEND = auto()   # 展开这一层的子文件夹
  STOP = auto()      # 停止：子文件夹保留为 children=None 的整体单元
  SKIP = auto()      # 这个文件夹整个从树里剔除


@dataclass
class FolderCtx:
  """策略的输入：当前站在哪个文件夹、看到了什么

  entries 为 None 表示"进入前探测"（还没列出内容）：
    只看名字/路径/深度就能判断的策略此时即可返回 STOP/SKIP，
    walker 会省掉一次进入+列出的导航；
    需要 entries 的策略此时应返回 None 弃权，等列出后的第二次调用。
  """
  name: str
  path: str
  depth: int
  entries: Optional[List[EntryInfo]] = None


StopPolicy = Callable[[FolderCtx], Optional[WalkAction]]
Lister = Callable[[str], Awaitable[List[EntryInfo]]]


def _match_any(name: str, patterns) -> bool:
  return any(fnmatch.fnmatchcase(name, p) for p in patterns)


def max_depth(n: int) -> StopPolicy:
  """递归深度上限：depth >= n 的文件夹不再展开子级（根 depth=0）"""
  def policy(ctx: FolderCtx) -> Optional[WalkAction]:
    if ctx.depth >= n:
      return WalkAction.STOP
    return None
  return policy


def stop_folder(*patterns) -> StopPolicy:
  """名字匹配(glob)的文件夹是终点：不进入它，保留为整体单元"""
  def policy(ctx: FolderCtx) -> Optional[WalkAction]:
    if _match_any(ctx.name, patterns):
      return WalkAction.STOP
    return None
  return policy


def stop_when_child(*patterns) -> StopPolicy:
  """当前层的子文件夹里出现名字匹配(glob)时，本层即终点：不再进入任何子文件夹"""
  def policy(ctx: FolderCtx) -> Optional[WalkAction]:
    if ctx.entries is None:
      return None
    for ent in ctx.entries:
      if ent.is_dir and _match_any(ent.name, patterns):
        return WalkAction.STOP
    return None
  return policy


def skip(*patterns) -> StopPolicy:
  """名字匹配(glob)的文件夹整个剔除，不进树"""
  def policy(ctx: FolderCtx) -> Optional[WalkAction]:
    if _match_any(ctx.name, patterns):
      return WalkAction.SKIP
    return None
  return policy


def chain(*policies: StopPolicy) -> StopPolicy:
  """依次询问，第一个返回非 None 的策略生效"""
  def policy(ctx: FolderCtx) -> Optional[WalkAction]:
    for p in policies:
      action = p(ctx)
      if action is not None:
        return action
    return None
  return policy


def _join_path(parent_path: str, name: str) -> str:
  if parent_path == "/":
    return "/" + name
  return parent_path.rstrip("/") + "/" + name


async def walk_tree(lister: Lister,
                    policy: Optional[StopPolicy] = None,
                    root_name: str = "全部文件") -> PanNode:
  """从分享根做 DFS，产出策略裁剪后的目录树

  每个文件夹策略最多被调用两次（进入前探测 / 列出内容后），
  lister 只会为"确实要进入"的文件夹调用一次。
  """
  async def walk(name: str, path: str, depth: int) -> Optional[PanNode]:
    action = policy(FolderCtx(name, path, depth, None)) if policy else None
    if action == WalkAction.SKIP:
      return None
    if action == WalkAction.STOP:
      return PanNode(name, True, path, depth)

    entries = await lister(path)
    action = policy(FolderCtx(name, path, depth, entries)) if policy else None
    if action == WalkAction.SKIP:
      return None

    children: List[Optional[PanNode]] = [
      PanNode(e.name, e.is_dir, _join_path(path, e.name), depth + 1,
              e.size_text, e.mtime_text)
      for e in entries
    ]

    if action != WalkAction.STOP:
      for i, e in enumerate(entries):
        if not e.is_dir:
          continue
        children[i] = await walk(e.name, _join_path(path, e.name), depth + 1)

    node = PanNode(name, True, path, depth)
    node.children = [c for c in children if c is not None]
    return node

  return await walk(root_name, "/", 0)


def format_tree(root: PanNode) -> str:
  """树的可读文本形式，脚本 dry-run 时打印给人工核对"""
  lines: List[str] = []

  def rec(n: PanNode):
    marker = "[D]" if n.is_dir else "[F]"
    meta = "  ".join(x for x in (n.size_text, n.mtime_text) if x)
    unexpanded = "  (未展开)" if n.is_leaf_unit() else ""
    line = "  " * n.depth + f"{marker} {n.name}"
    if meta:
      line += f"  | {meta}"
    lines.append(line + unexpanded)
    if n.children:
      for c in n.children:
        rec(c)

  rec(root)
  return "\n".join(lines)
