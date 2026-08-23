"""百度盘转存编排（cangku consume 阶段）：分享树 -> 增量转存计划。

从 playground/bd_orchestrate_dryrun.py 升包。选点核心思路：
  分享根目录按作者分道 —— 本地库（local_library.db，NAS 已确认库镜像）无记录的
  作者整目录全转存；已匹配作者 walk 到月份层做增量对比，转存目标 =
  最后已抓取月（防当月没抓完，精确补齐只挑本地没有的子项）+ 其他未覆盖月。

绝大多数函数是纯逻辑（用假树即可单测，见 tests/test_baidu_pan_orchestrate.py）；
expand_month_node / select_ops 需要一个打开的分享页（重抓月按需展开一级）。
正式入口 scripts/consume_posts.py。
"""
import json
import logging
import sqlite3
from dataclasses import dataclass
from typing import Optional

from scrape_all.local_library.parse import YEAR_DIR_RE, month_of
from scrape_all.sites.baidu_pan.save_plan import build_save_plan
from scrape_all.sites.baidu_pan.tree import FolderCtx, PanNode, WalkAction, chain, skip

# 作者别名：分享根目录名 / box_title 与本地库作者名对不上时的人工映射
# （大小写差异 casefold 自动处理；这里只放自动匹配不了的，如罗马字 vs 片假名、繁简 鱼/魚）
CREATOR_ALIASES = {
    "reel": "リル",          # 罗马字（box_title 也救不回时兜底）
    "harechippai": "はれ",   # box_title 是通用词"合集"，walk 目录名是罗马字
}


@dataclass
class ShareLink:
  """一条待转存的分享链接（从 cangku stat=2 帖子的 links_json 装配）"""
  post_url: str             # 帖子 url（stat 标记的主键）
  post_id: str              # 帖子 id（url 末段，人工指定用）
  title: str
  url: str                  # pan.baidu.com 分享链接
  pwd: Optional[str]        # 提取码
  box_title: str            # 合集卡标题（作者匹配的第二来源）


# ---------------------------------------------------------------- walk 策略

def stop_at_year_level(ctx: FolderCtx):
  """到父节点是年份即可：当前目录名是月份 token，或父目录名是纯 4 位年份 -> 整体单元不展开。

  同时覆盖两种结构：year_nested (/作者/2025/25.08) 与 month_flat (/作者/25.08)。
  名字判断不依赖 entries，进入前探测即可返回，省一次导航。
  """
  if month_of(ctx.name):
    return WalkAction.STOP
  path = ctx.path.rstrip("/")
  cut = path.rfind("/")
  if cut > 0 and YEAR_DIR_RE.match(path[:cut].rsplit("/", 1)[-1]):
    return WalkAction.STOP
  return None


def make_policy(local: dict = None, box_title: str = ""):
  """walk 策略工厂（按链接构造）。

  - 广告目录剔除
  - 未匹配作者（local 给出，且目录名/box_title/别名都找不到）在作者层即停：
    整目录作为转存单元，不往里 walk —— 新作者反正要全转存，月份粒度没有意义
  - 已匹配作者走 stop_at_year_level（年份展开一级，月份为整体单元）
  local 为 None 时不做作者层判断（自测/纯结构 walk 用）。
  """
  def stop_if_new_creator(ctx: FolderCtx):
    if ctx.depth == 1 and local is not None:
      if resolve_local(ctx.name, box_title, local)[0] is None:
        return WalkAction.STOP
    return None

  return chain(
      skip("保存资源自動領取優惠卷*"),
      stop_if_new_creator,
      stop_at_year_level,
  )


# ---------------------------------------------------------------- 树 -> 作者月份

def share_month_of(name: str):
  """分享侧的月份 token 识别：比 NAS 侧 month_of 多一层"剥扩展名再试"。

  分享合集里大量存在 "年份/25.10.mp4" 这种散文件（NAS 侧正则故意排除 "22.1.jpg"
  页码图，对分享侧太严）。误报风险：月份目录内部的页码图看不见（单元不展开），可见的
  只有作者/年份层的散文件，合集分享里这些就是月份正主。
  """
  mo = month_of(name)
  if mo is None and "." in name:
    mo = month_of(name.rsplit(".", 1)[0])
  return mo


def collect_months_under(node: PanNode):
  """单个作者子树 -> {"months": {月份: [节点路径...]}, "odd": [异常节点名]}

  月份来源：月份 token 的目录单元（year_nested/month_flat 皆是），以及带日期前缀的散文件。
  odd：年份目录下不是月份 token 的目录（结构异常，只报告）。
  新作者被策略停在作者层时 children 为 None，months 为空（不参与增量对比）。
  """
  info = {"months": {}, "odd": []}

  def rec(n: PanNode):
    for ch in n.children or []:
      mo = share_month_of(ch.name)
      if ch.is_dir:
        if ch.is_leaf_unit():
          if mo:
            info["months"].setdefault(mo, []).append(ch.path)
          elif n.depth >= 2:   # 年份下的非月份目录才算异常，作者层的说明文件不算
            info["odd"].append(ch.path)
        else:
          rec(ch)
      else:
        if mo:                    # 带日期的散文件也算"网盘里有这个月"
          info["months"].setdefault(mo, []).append(ch.path)

  rec(node)
  return info


def collect_creator_months(root: PanNode):
  """walk 后的树 -> {creator: {"months":…, "odd":…}}（顶层目录逐个，自测用）"""
  creators = {}
  for c in root.children or []:
    if c.is_dir:
      creators[c.name] = collect_months_under(c)
  return creators


# ---------------------------------------------------------------- 对比本地库

def compute_targets(share_months, db_months):
  """转存目标 = 最后已抓取月（防当月没抓完） + 未覆盖月。

  db_months 为 None 表示本地库无此作者（新作者，全部未覆盖）。
  返回 (selected_months, detail)。
  """
  if db_months is None:
    return set(share_months), {
        "kind": "新作者", "resave": None,
        "uncovered": sorted(share_months), "skipped": [], "db_only": []}
  resave = max(db_months)
  selected = {resave} | (set(share_months) - set(db_months))
  selected &= set(share_months)     # 分享里没有的月份无从转存
  return selected, {
    "kind": "增量", "resave": resave if resave in share_months else None,
    "uncovered": sorted(set(share_months) - set(db_months)),
    "skipped": sorted((set(share_months) & set(db_months)) - {resave}),
    "db_only": sorted(set(db_months) - set(share_months))}


# ---------------------------------------------------------------- 重抓月精确补齐

def month_covered_names(local_paths) -> set:
  """该月的本地相对路径 -> 已覆盖的名字集合（每条路径的最后一段，去首尾空白）。

  分享侧目录/文件名带尾随空格的不少（如 "阿比盖尔·威廉姆斯 "），比较时两边都 strip。
  月份文件夹自身也在路径里（month_flat 的第一条就是月目录），其名字参与比较无害。
  """
  return {p.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].strip()
          for p in local_paths if p}


def name_covered(name: str, covered: set) -> bool:
  return name.strip() in covered


def find_node(root: PanNode, path: str):
  """按 path 在（walk 裁剪过的）树里找节点；找不到返回 None"""
  if path == "/":
    return root
  node = root
  for seg in path.strip("/").split("/"):
    node = next((c for c in node.children or [] if c.name == seg), None)
    if node is None:
      return None
  return node


# ---------------------------------------------------------------- 目标路径映射

def make_target_for(creator_roots: dict, target_base: str):
  """source_dir -> 目标路径：把分享路径的作者层替换成该作者的目标根。

  creator_roots = {分享侧作者名: 目标根}：
    已匹配作者 -> target_base/本地 rel_path（[yejiang]/作者/…），层级不变，
                 转存后搬运回 NAS 是纯复制零改名
    未匹配作者 -> 兜底 target_base/<分享侧作者名>（正常走根级 op，见下）
  根级 op（"/"，只会在全转存新作者时出现）-> target_base/[yejiang]，
  即所有内容统一落 [yejiang] 下。
  """
  def target(source_dir: str) -> str:
    stripped = source_dir.strip("/")
    if not stripped:
      return f"{target_base.rstrip('/')}/[yejiang]"
    first, _, rest = stripped.partition("/")
    root = creator_roots.get(first) or f"{target_base.rstrip('/')}/[yejiang]/{first}"
    return f"{root}/{rest}" if rest else root
  return target


async def expand_month_node(link_page, node: PanNode) -> None:
  """把一个未展开的目录单元就地展开一层（children=None -> 子节点列表，子目录仍是单元）。

  只用于重抓月的精确补齐；失败抛异常，调用方回退整月转存。
  """
  await link_page.goto_path(node.path)
  entries = await link_page.list_files()
  node.children = [
      PanNode(e.name, e.is_dir,
              node.path.rstrip("/") + "/" + e.name, node.depth + 1,
              e.size_text, e.mtime_text)
      for e in entries
  ]


# ---------------------------------------------------------------- 作者匹配

def resolve_local(creator: str, box_title: str, local: dict):
  """分享里的作者名 -> 本地库记录 (显示名, rel_path, months, month_paths)。

  匹配顺序：分享目录名 casefold -> box_title casefold -> 别名表。
  返回 (记录, 命中方式描述)；未命中返回 (None, None)。
  """
  for cand, how in ((creator, "目录名"), (box_title, f"box_title {box_title!r}")):
    if cand and cand.casefold() in local:
      return local[cand.casefold()], how
  for cand in (creator, box_title):
    mapped = CREATOR_ALIASES.get((cand or "").casefold())
    if mapped and mapped.casefold() in local:
      return local[mapped.casefold()], f"别名表 {cand!r}->{mapped!r}"
  return None, None


# ---------------------------------------------------------------- 数据装配

def load_local_months(db_path: str):
  """local_library.db -> {creator.casefold(): (显示名, rel_path, 月份set, {月份: [本地路径]})}

  downloaded_months 兼容两种形态：{月份: [相对路径...]}（现行）/ [月份, ...]（旧）。
  旧形态没有路径明细 -> 重抓月精确补齐自动退回整月转存。
  """
  con = sqlite3.connect(db_path)
  con.row_factory = sqlite3.Row
  out = {}
  for r in con.execute("SELECT creator, rel_path, content_json FROM LibraryFolder"):
    data = json.loads(r["content_json"] or "{}").get("downloaded_months") or {}
    if isinstance(data, dict):
      months, month_paths = set(data), {m: list(v or []) for m, v in data.items()}
    else:
      months, month_paths = set(data), {}
    out[r["creator"].casefold()] = (r["creator"], (r["rel_path"] or "").strip("/"),
                                    months, month_paths)
  con.close()
  return out


# ---------------------------------------------------------------- 选点主流程

def fmt_months(months):
  return " ".join(months) if months else "(无)"


async def select_ops(link_page, tree: PanNode, link: ShareLink, local: dict,
                     emit, target_base: str):
  """walk 完的树 -> 转存操作列表：逐作者分道（新作者整目录/已匹配增量）+ 重抓月精确补齐。

  dry-run 与真跑共用这一段，保证两边选中的内容完全一致。
  emit(line) 负责过程明细输出；重抓月展开要用 link_page（页面须保持打开）。
  """
  selected_paths = set()
  creator_roots = {}          # 分享侧作者名 -> 转存目标根（镜像本地 rel_path）
  n_creators = 0
  for c in tree.children or []:
    if not c.is_dir:
      continue
    n_creators += 1
    creator = c.name
    db, how = resolve_local(creator, link.box_title, local)

    if db is None:
      emit(f"  作者 {creator}  [本地库无记录 -> 整目录全转存（不 walk）]")
      selected_paths.add(c.path)
      continue

    creator_roots[creator] = (f"{target_base.rstrip('/')}/{db[1]}" if db[1]
                              else f"{target_base.rstrip('/')}/[yejiang]/{creator}")
    info = collect_months_under(c)
    share_months = set(info["months"])
    selected, detail = compute_targets(share_months, db[2])
    month_paths = db[3]

    emit(f"  作者 {creator}  [本地库 {db[0]}（{db[1]}），{len(db[2])} 个月，"
         f"最后抓取 {max(db[2])}；匹配: {how}]")
    emit(f"    分享有 {len(share_months)} 个月: {fmt_months(sorted(share_months))}")
    emit(f"    转存 {len(selected)} 个月"
         + (f"（重抓最后月 {detail['resave']}）" if detail["resave"] else "")
         + (f" + 未覆盖 {fmt_months(detail['uncovered'])}" if detail["uncovered"] else ""))
    if detail["skipped"]:
      emit(f"    跳过已覆盖 {len(detail['skipped'])} 个月: {fmt_months(detail['skipped'])}")
    if detail["db_only"]:
      emit(f"    注意: 本地有而分享没有 {len(detail['db_only'])} 个月: "
           f"{fmt_months(detail['db_only'])}")
    if info["odd"]:
      emit(f"    !! 结构异常目录(不选): {info['odd']}")

    for mo in selected:
      if mo == detail.get("resave") and month_paths.get(mo) is not None:
        # 重抓月精确补齐：本地路径已知该月有什么 -> 只挑本地没有的子项
        covered = month_covered_names(month_paths[mo])
        for upath in info["months"].get(mo, []):
          node = find_node(tree, upath)
          if node is None or (node.is_dir and not node.is_leaf_unit()):
            selected_paths.add(upath)          # 树里对不上，保守整月转存
            continue
          if not node.is_dir:                  # 散文件单元：按名字判
            if name_covered(node.name, covered):
              emit(f"    重抓月 {mo}: {node.name} 本地已有，跳过")
            else:
              selected_paths.add(upath)
            continue
          try:
            await expand_month_node(link_page, node)
          except Exception as e:
            logging.warning(f"重抓月 {mo} 展开失败 {upath}: {e}，回退整月转存")
            selected_paths.add(upath)
            continue
          missing = [c2 for c2 in node.children if not name_covered(c2.name, covered)]
          if not node.children:
            emit(f"    重抓月 {mo}: 分享里是空目录，跳过")
          elif not missing:
            emit(f"    重抓月 {mo} 已完整（{len(node.children)} 项全在本地），不重抓")
          else:
            selected_paths.update(c2.path for c2 in missing)
            have = len(node.children) - len(missing)
            emit(f"    重抓月 {mo} 精确补齐: 本地已有 {have}/{len(node.children)} 项，"
                 f"补 {len(missing)}: {', '.join(c2.name for c2 in missing)}")
      else:
        selected_paths.update(info["months"].get(mo, []))

  if n_creators == 0:
    emit("  (根下没有目录?)")
  return build_save_plan(tree, want=lambda n: n.path in selected_paths,
                         target_for=make_target_for(creator_roots, target_base))
