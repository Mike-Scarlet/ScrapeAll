
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
logging.basicConfig(
  level=logging.NOTSET,
  format="[%(asctime)s] %(message)s",
)

from scrape_all.browser.session import BrowserSession
from scrape_all.sites.baidu_pan.errors import BaiduPanError
from scrape_all.sites.baidu_pan.pages.shared_link_page import SharedLinkPage
from scrape_all.sites.baidu_pan.walker import ShareWalker
from scrape_all.sites.baidu_pan.tree import PanNode, chain, skip, stop_below, format_tree
from scrape_all.sites.baidu_pan.save_plan import build_save_plan, flat_to, format_plan
from scrape_all.sites.baidu_pan.save_executor import execute_save_plan, format_results
from config import BAIDU_PAN_PROXY_SERVER, WALK_LINKS

# 部分转存：walk(只读) -> 生成计划 -> 打印 -> 人工确认 -> 执行 -> 汇总
# --dry-run 只打印不执行（不做任何选择/转存）

# 与 walk_share.py 相同的遍历策略：广告目录剔除，20* 年份目录只展开一级（月份为整体单元）
POLICY = chain(
  skip("保存资源自動領取優惠卷*"),
  stop_below("20*"),
)

# 本次要转存的内容：勾选 = 路径命中 WANT_PATHS 的节点（选中文件夹 = 整棵子树带走）
WANT_PATHS = {
  "/Mimu/2025/25.08",
  "/Mimu/2025/25.09",
}

# 目标：全部平铺存到同一目录（如 25.08 -> /test_save/ver1/25.08）
TARGET_DIR = "/test_save/ver1"


def want(node: PanNode) -> bool:
  return node.path in WANT_PATHS


DRY_RUN = "--dry-run" in sys.argv


async def main():
  plans = []   # (link, SharedLinkPage, ops)；页面保持打开，执行阶段直接复用
  async with BrowserSession(BAIDU_PAN_PROXY_SERVER) as session:
    for link in WALK_LINKS:
      try:
        link_page = await SharedLinkPage.open(session.context, link)
      except BaiduPanError as e:
        logging.error(f"skip link {link}: {e}")
        continue

      try:
        tree = await ShareWalker(link_page).walk(POLICY)
      except BaiduPanError as e:
        logging.error(f"walk failed {link}: {e}")
        await link_page.page.close()
        continue

      ops = build_save_plan(tree, want=want, target_for=flat_to(TARGET_DIR))
      plans.append((link, link_page, ops))

      print(f"\n=== {link}")
      print(format_tree(tree))
      print("\n--- save plan")
      print(format_plan(ops))

    if DRY_RUN:
      print("\n[dry-run] 计划打印完毕，未做任何选择/转存")
      return

    total = sum(len(ops) for _, _, ops in plans)
    if total == 0:
      print("\n没有可转存的内容（计划为空），退出")
      return

    try:
      answer = input(f"\n共 {total} 个转存操作，确认无误请输入 yes 开始执行: ")
    except EOFError:
      answer = ""
    if answer.strip() != "yes":
      print("未确认，什么都不做，退出")
      return

    for link, link_page, ops in plans:
      if not ops:
        continue
      print(f"\n=== saving {link}")
      results = await execute_save_plan(link_page, ops)
      print(format_results(results))

    try:
      input("\ndone, press enter to close browser ")
    except EOFError:
      pass

asyncio.run(main())
