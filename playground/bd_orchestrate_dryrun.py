"""百度网盘转存编排原型（只读 dry-run，不做任何转存）。

流程：
  1. 从 cangku.db 取 stat=2 帖子的百度盘分享链接
  2. Playwright 打开分享，walk 目录树 —— 策略：到父节点是年份即可
     （年份目录展开一级；月份 token 目录为整体单元；month_flat 平铺结构同样停在月份层）
  3. 对比 local_library.db 的 downloaded_months：
     转存目标 = 最后一个已抓取的月份（防当月没抓完） + 其他未覆盖的月份
  4. 打印对比报告 + 转存计划（build_save_plan）；目标目录暂用 mirror 占位，待定

用法：
  python playground/bd_orchestrate_dryrun.py --ids 225896,216571   # 指定帖子 id
  python playground/bd_orchestrate_dryrun.py --limit 3             # 最新 3 个帖子
  python playground/bd_orchestrate_dryrun.py --test                # config.TEST_LINKS
  python playground/bd_orchestrate_dryrun.py                       # 全部（35 个左右，慢）
可选： --show-tree 控制台也打印目录树；报告全文落 data/bd_orchestrate_report.txt
"""
import asyncio
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
from scrape_all.sites.baidu_pan.save_plan import build_save_plan, format_plan, mirror_from
from scrape_all.sites.baidu_pan.tree import (FolderCtx, PanNode, WalkAction, chain,
                                             format_tree, skip)
from scrape_all.sites.baidu_pan.walker import ShareWalker
from config import BAIDU_PAN_PROXY_SERVER, TEST_LINKS

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CANGKU_DB = os.path.join(DATA, "cangku.db")
LOCAL_DB = os.path.join(DATA, "local_library.db")
REPORT = os.path.join(DATA, "bd_orchestrate_report.txt")

# 目标目录占位（编排真跑前的开放决策：镜像/平铺/按作者），dry-run 只展示
TARGET_BASE = "/转存待定"

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


POLICY = chain(
  skip("保存资源自動領取優惠卷*"),   # 广告目录剔除（与 walk_share.py 一致）
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

def collect_creator_months(root: PanNode):
  """walk 后的树 -> {creator: {"months": {月份: [节点路径...]}, "odd": [异常节点名]}}

  月份来源：月份 token 的目录单元（year_nested/month_flat 皆是），以及带日期前缀的散文件。
  odd：年份目录下不是月份 token 的目录（结构异常，只报告）。
  """
  creators = {}
  for c in root.children or []:
    if not c.is_dir:
      continue
    info = {"months": {}, "odd": []}
    creators[c.name] = info

    def rec(node: PanNode):
      for ch in node.children or []:
        mo = share_month_of(ch.name)
        if ch.is_dir:
          if ch.is_leaf_unit():
            if mo:
              info["months"].setdefault(mo, []).append(ch.path)
            elif node.depth >= 2:   # 年份下的非月份目录才算异常，作者层的说明文件不算
              info["odd"].append(ch.path)
          else:
            rec(ch)
        else:
          if mo:                    # 带日期的散文件也算"网盘里有这个月"
            info["months"].setdefault(mo, []).append(ch.path)

    rec(c)
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


# ---------------------------------------------------------------- 纯逻辑：作者匹配

def resolve_local(creator: str, box_title: str, local: dict):
  """分享里的作者名 -> 本地库记录。

  匹配顺序：分享目录名 casefold -> box_title casefold -> 别名表。
  返回 (local条目, 命中方式描述)；未命中返回 (None, None)。
  """
  for cand, how in ((creator, "目录名"), (box_title, f"box_title {box_title!r}")):
    if cand and cand.casefold() in local:
      return local[cand.casefold()], how
  for cand in (creator, box_title):
    mapped = CREATOR_ALIASES.get((cand or "").casefold())
    if mapped and mapped.casefold() in local:
      return local[mapped.casefold()], f"别名表 {cand!r}->{mapped!r}"
  return None, None


def suggest_creators(share_months: set, local: dict, top_n=3):
  """未命中时的建议：按月份重合度猜本地库作者（只建议，不自动采用）。

  门槛：重合 >= 10 个月且 >= 60% 本地月份 —— 低于此基本是"近期月份撞车"的噪音
  （实测 Dim vs はれ 50%、NFFA vs セネト 59% 都是噪音；harechippai vs はれ 98% 是真命中）。
  """
  scored = []
  for cf_key, (name, months) in local.items():
    overlap = len(share_months & months)
    if overlap >= 10 and overlap / max(1, len(months)) >= 0.6:
      scored.append((overlap, name))
  scored.sort(reverse=True)
  return [f"{name} (重合 {n} 个月)" for n, name in scored[:top_n]]


# ---------------------------------------------------------------- 数据库读取

def load_local_months():
  """local_library.db -> {creator.casefold(): (creator显示名, downloaded_months set)}"""
  con = sqlite3.connect(LOCAL_DB)
  con.row_factory = sqlite3.Row
  out = {}
  for r in con.execute("SELECT creator, content_json FROM LibraryFolder"):
    months = set(json.loads(r["content_json"] or "{}").get("downloaded_months") or [])
    out[r["creator"].casefold()] = (r["creator"], months)
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
  for a in args:
    if a.startswith("--ids="):
      ids = [x for x in a[6:].split(",") if x]
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
        for attempt in (1, 2):
          try:
            link_page = await SharedLinkPage.open(session.context, link["url"],
                                                  password=link["pwd"])
            tree = await ShareWalker(link_page).walk(POLICY)
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
        await link_page.page.close()   # dry-run 只读，walk 完就关页

        if show_tree:
          print(format_tree(tree))
        report.write(format_tree(tree) + "\n")

        creators = collect_creator_months(tree)
        if not creators:
          emit("  (根下没有目录?)")
          continue

        # 聚合本链接内每个作者的选中月份
        selected_paths = set()
        for creator, info in creators.items():
          share_months = set(info["months"])
          db, how = resolve_local(creator, link["box_title"], local)
          selected, detail = compute_targets(share_months, db[1] if db else None)

          if db:
            emit(f"  作者 {creator}  [本地库 {db[0]}，{len(db[1])} 个月，"
                 f"最后抓取 {max(db[1])}；匹配: {how}]")
          else:
            line = f"  作者 {creator}  [本地库无记录 -> 按新作者处理，全部转存]"
            sug = suggest_creators(share_months, local)
            if sug:
              line += f"  疑似别名: {'; '.join(sug)}"
            emit(line)

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
            selected_paths.update(info["months"].get(mo, []))

        ops = build_save_plan(tree, want=lambda n: n.path in selected_paths,
                              target_for=mirror_from(TARGET_BASE))
        total_ops.extend((link["post_id"], op) for op in ops)
        report.write("--- save plan (target 为占位，待定)\n")
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
