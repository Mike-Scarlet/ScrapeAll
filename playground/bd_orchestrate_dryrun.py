"""百度网盘转存编排原型（只读 dry-run，不做任何转存）。

流程：
  1. 从 cangku.db 取 stat=2 帖子的百度盘分享链接
  2. Playwright 打开分享，只列根目录分作者，然后按作者分道：
     - 本地库无记录（新作者）-> 没有增量的意义：walk 在作者层即停，
       整目录作为一次转存单元（也不进年份/月份层，快）
     - 已有记录 -> walk 到父节点是年份即可（年份目录展开一级，月份 token 目录
       为整体单元；month_flat 平铺结构同样停在月份层），做增量对比：
       转存目标 = 最后一个已抓取的月份（防当月没抓完） + 其他未覆盖的月份
  3. 重抓月精确补齐：本地路径给出该月已有内容的名字，把该月的目录单元在分享里
     展开一层，只挑本地没有的子项（同名视为已有；"xx new.mp4" 这类改名新版会选中）；
     全都在 -> 该月已完整，不重抓。展开失败回退整月转存。
  4. 打印对比报告 + 转存计划（build_save_plan）。目标统一落 /扒/<运行日期>/[yejiang]/：
     已匹配作者镜像本地库 rel_path（搬运回 NAS 零改名），新作者用分享侧作者名

用法：
  python playground/bd_orchestrate_dryrun.py --ids 225896,216571   # 指定帖子 id
  python playground/bd_orchestrate_dryrun.py --limit 3             # 最新 3 个帖子
  python playground/bd_orchestrate_dryrun.py --test                # config.TEST_LINKS
  python playground/bd_orchestrate_dryrun.py                       # 全部（35 个左右，慢）
可选： --show-tree 控制台也打印目录树；报告全文落 data/bd_orchestrate_report.txt
"""
import asyncio
import datetime
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *  # noqa
import logging

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

from scrape_all.browser.session import BrowserSession
from scrape_all.local_library.parse import YEAR_DIR_RE, month_of
from scrape_all.sites.baidu_pan.errors import BaiduPanError
from scrape_all.sites.baidu_pan.pages.shared_link_page import SharedLinkPage
from scrape_all.sites.baidu_pan.save_plan import build_save_plan, format_plan
from scrape_all.sites.baidu_pan.tree import (FolderCtx, PanNode, WalkAction, chain,
                                             format_tree, skip)
from scrape_all.sites.baidu_pan.walker import ShareWalker
from config import BAIDU_PAN_PROXY_SERVER, TEST_LINKS

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CANGKU_DB = os.path.join(DATA, "cangku.db")
LOCAL_DB = os.path.join(DATA, "local_library.db")
REPORT = os.path.join(DATA, "bd_orchestrate_report.txt")

# 转存目标根：/扒/<运行日期>（按跑的日期分批，如 /扒/20260818）；
# 其下统一 [yejiang]/作者/，已匹配作者镜像本地库 rel_path
TARGET_BASE = f"/扒/{datetime.date.today():%Y%m%d}"

# 作者别名：分享根目录名 / box_title 与本地库作者名对不上时的人工映射
# （大小写差异 casefold 自动处理；这里只放自动匹配不了的，如罗马字 vs 片假名、繁简 鱼/魚）
CREATOR_ALIASES = {
    "reel": "リル",          # 罗马字（box_title 也救不回时兜底）
    "harechippai": "はれ",   # box_title 是通用词"合集"，walk 目录名是罗马字
}


# ---------------------------------------------------------------- 纯逻辑：walk 策略

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

  - 广告目录剔除（与 walk_share.py 一致）
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


# ---------------------------------------------------------------- 纯逻辑：树 -> 作者月份

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


# ---------------------------------------------------------------- 纯逻辑：对比本地库

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


# ---------------------------------------------------------------- 纯逻辑：重抓月精确补齐

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


def make_target_for(creator_roots: dict):
  """source_dir -> 目标路径：把分享路径的作者层替换成该作者的目标根。

  creator_roots = {分享侧作者名: 目标根}：
    已匹配作者 -> TARGET_BASE/本地 rel_path（[yejiang]/作者/…），层级不变，
                 转存后搬运回 NAS 是纯复制零改名
    未匹配作者 -> 兜底 TARGET_BASE/<分享侧作者名>（正常走根级 op，见下）
  根级 op（"/"，只会在全转存新作者时出现）-> TARGET_BASE/[yejiang]，
  即所有内容统一落 [yejiang] 下。
  """
  def target(source_dir: str) -> str:
    stripped = source_dir.strip("/")
    if not stripped:
      return f"{TARGET_BASE.rstrip('/')}/[yejiang]"
    first, _, rest = stripped.partition("/")
    root = creator_roots.get(first) or f"{TARGET_BASE.rstrip('/')}/[yejiang]/{first}"
    return f"{root}/{rest}" if rest else root
  return target


async def expand_month_node(link_page: SharedLinkPage, node: PanNode) -> None:
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


# ---------------------------------------------------------------- 纯逻辑：作者匹配

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


# ---------------------------------------------------------------- 数据库读取

def load_local_months():
  """local_library.db -> {creator.casefold(): (显示名, rel_path, 月份set, {月份: [本地路径]})}

  downloaded_months 兼容两种形态：{月份: [相对路径...]}（现行）/ [月份, ...]（旧）。
  旧形态没有路径明细 -> 重抓月精确补齐自动退回整月转存。
  """
  con = sqlite3.connect(LOCAL_DB)
  con.row_factory = sqlite3.Row
  out = {}
  for r in con.execute("SELECT creator, rel_path, content_json FROM LibraryFolder"):
    data = json.loads(r["content_json"] or "{}").get("downloaded_months") or {}
    if isinstance(data, dict):
      months, month_paths = set(data), {m: list(v or []) for m, v in data.items()}
    else:
      months, month_paths = set(data), {}
    out[r["creator"].casefold()] = (r["creator"], (r["rel_path"] or "").strip("/"), months, month_paths)
  con.close()
  return out


def load_share_links(ids=None, limit=None):
  """cangku.db stat=2 -> [{post_id, title, url, pwd, box_title}]，新帖在前"""
  con = sqlite3.connect(CANGKU_DB)
  con.row_factory = sqlite3.Row
  rows = con.execute(
      "SELECT url, title, links_json FROM PostItem "
      "WHERE stat=2 AND links_json IS NOT NULL AND links_json != ''").fetchall()
  con.close()
  out = []
  for r in rows:
    links = json.loads(r["links_json"])
    baidu = [l for l in links
             if l.get("pan_type") == "baidu" or "pan.baidu.com" in (l.get("url") or "")]
    if not baidu:
      continue
    l = baidu[0]
    post_id = r["url"].rstrip("/").split("/")[-1]
    out.append({"post_id": post_id, "title": r["title"],
                "url": l["url"], "pwd": l.get("pwd") or None,
                "box_title": l.get("box_title") or ""})
  out.sort(key=lambda x: int(x["post_id"]) if x["post_id"].isdigit() else 0, reverse=True)
  if ids:
    want = {str(i) for i in ids}
    out = [x for x in out if x["post_id"] in want]
  if limit:
    out = out[:limit]
  return out


# ---------------------------------------------------------------- 主流程

def fmt_months(months):
  return " ".join(months) if months else "(无)"


async def main():
  args = sys.argv[1:]
  show_tree = "--show-tree" in args
  use_test = "--test" in args

  ids, limit = None, None
  for i, a in enumerate(args):
    if a.startswith("--ids="):
      ids = [x for x in a[6:].split(",") if x]
    elif a == "--ids" and i + 1 < len(args):   # 文档里的空格形式
      ids = [x for x in args[i + 1].split(",") if x]
    elif a.startswith("--limit="):
      limit = int(a[7:])

  if use_test:
    links = [{"post_id": "TEST", "title": "TEST_LINKS", "url": u, "pwd": None,
              "box_title": ""} for u in TEST_LINKS]
  else:
    links = load_share_links(ids=ids, limit=limit)
  if not links:
    print("没有可处理的链接")
    return

  local = load_local_months()
  print(f"本地库作者 {len(local)} 个；分享链接 {len(links)} 个\n")

  total_ops = []
  with open(REPORT, "w", encoding="utf-8") as report:

    def emit(line=""):
      print(line)
      report.write(line + "\n")

    async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
      for li, link in enumerate(links, 1):
        head = f"[{li}/{len(links)}] post {link['post_id']}  {link['title'][:40]}"
        print(f"\n=== {head}")
        report.write(f"\n{'=' * 70}\n{head}\nlink: {link['url']}\n")

        # open + walk 整体重试一次（实测偶发 30s open 超时、walk 中途页面状态丢失）
        tree = None
        link_page = None
        policy = make_policy(local, link["box_title"])
        for attempt in (1, 2):
          try:
            link_page = await SharedLinkPage.open(session.context, link["url"],
                                                  password=link["pwd"])
            tree = await ShareWalker(link_page).walk(policy)
            break
          except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if link_page is not None:
              await link_page.page.close()
              link_page = None
            dead = "share invalid" in str(e)   # 死链重试无意义
            if attempt == 1 and not dead:
              logging.warning(f"retry ({link['post_id']}): {msg}")
              await asyncio.sleep(3)
            else:
              emit(f"  !! failed, skip: {msg}")
              break
        if tree is None:
          continue

        # 逐作者分道：未匹配 -> 整目录单元全转存（walk 已停在作者层）；
        # 已匹配 -> 增量对比 + 重抓月精确补齐（要用页面，处理完再关）
        selected_paths = set()
        creator_roots = {}          # 分享侧作者名 -> 转存目标根（镜像本地 rel_path）
        n_creators = 0
        for c in tree.children or []:
          if not c.is_dir:
            continue
          n_creators += 1
          creator = c.name
          db, how = resolve_local(creator, link["box_title"], local)

          if db is None:
            emit(f"  作者 {creator}  [本地库无记录 -> 整目录全转存（不 walk）]")
            selected_paths.add(c.path)
            continue

          creator_roots[creator] = (f"{TARGET_BASE.rstrip('/')}/{db[1]}" if db[1]
                                    else f"{TARGET_BASE.rstrip('/')}/[yejiang]/{creator}")
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
                missing = [c for c in node.children if not name_covered(c.name, covered)]
                if not node.children:
                  emit(f"    重抓月 {mo}: 分享里是空目录，跳过")
                elif not missing:
                  emit(f"    重抓月 {mo} 已完整（{len(node.children)} 项全在本地），不重抓")
                else:
                  selected_paths.update(c.path for c in missing)
                  have = len(node.children) - len(missing)
                  emit(f"    重抓月 {mo} 精确补齐: 本地已有 {have}/{len(node.children)} 项，"
                       f"补 {len(missing)}: {', '.join(c.name for c in missing)}")
            else:
              selected_paths.update(info["months"].get(mo, []))

        if n_creators == 0:
          emit("  (根下没有目录?)")
        await link_page.page.close()

        if show_tree:
          print(format_tree(tree))
        report.write(format_tree(tree) + "\n")   # 重抓月展开后的最终树

        ops = build_save_plan(tree, want=lambda n: n.path in selected_paths,
                              target_for=make_target_for(creator_roots))
        total_ops.extend((link["post_id"], op) for op in ops)
        report.write("--- save plan（目标 = 转存到自己网盘，镜像本地库布局）\n")
        report.write(format_plan(ops) + "\n")
        report.flush()
        await asyncio.sleep(2)   # 链接间停一下，降低风控风险

    # 汇总
    print(f"\n{'=' * 70}")
    report.write(f"\n{'=' * 70}\n合计 {len(total_ops)} 个转存操作（dry-run，未执行）\n")
    print(f"合计 {len(total_ops)} 个转存操作（dry-run，未执行）")
    for post_id, op in total_ops:
      line = f"  [{post_id}] {op.source_dir} -> {op.target_dir} : {', '.join(op.names)}"
      print(line)
      report.write(line + "\n")

  print(f"\n报告已写 {REPORT}")


if __name__ == "__main__":
  asyncio.run(main())
