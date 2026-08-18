
import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional, Tuple

from scrape_all.sites.baidu_pan.errors import BaiduPanError
from scrape_all.sites.baidu_pan.pages.save_dialog import SaveDialog
from scrape_all.sites.baidu_pan.pages.shared_link_page import SharedLinkPage
from scrape_all.sites.baidu_pan.save_plan import SaveOp

# 执行器：按计划逐个做"勾选 + 转存"。计划本身（build_save_plan）已人工确认过。

PageFactory = Callable[[], Awaitable[SharedLinkPage]]
"""开一个该分享的新页面（带 url/pwd）；per-op 换页与末级恢复用"""


@dataclass
class SaveOpResult:
  op: SaveOp
  ok: bool
  note: str = ""      # 失败/不确定时的补充说明


async def _missing_names(link_page: SharedLinkPage, names: List[str]) -> List[str]:
  """列出当前目录里看不到的名字；列表读不到视为全部缺失（由调用方异常分支处理）"""
  listed = {e.name for e in await link_page.list_files()}
  return sorted(set(names) - listed)


async def _swap_page(link_page: SharedLinkPage, dialog, page_factory: PageFactory) -> SharedLinkPage:
  """关旧页 -> 工厂开新页 -> 弹窗跟着换绑，返回新页"""
  try:
    await link_page.page.close()
  except Exception as e:
    logging.warning(f"close old page failed: {e}")
  new_page = await page_factory()
  dialog.page = new_page.page
  return new_page


async def _goto_and_select(link_page: SharedLinkPage, op: SaveOp,
                           attempt: int, recovery_wait: float) -> None:
  """就位 + 校验 + 勾选。attempt 2/3 先做恢复动作（Escape / 整页 reload）。

  校验是必须的：真跑实测 hash 跳转偶发"路由没反应"（不发 share/list、内容停在
  旧目录，10s 稳定等待照样通过），直接勾选会等 30s 超时；列目录比对名字能在
  勾选前暴露这种状态。恢复手段逐级加强，Escape 清残留遮罩，reload 重置 SPA。
  """
  if attempt == 2:
    logging.warning(f"就位校验失败，Escape 后重试: {op.source_dir}")
    await link_page.page.keyboard.press("Escape")
    await asyncio.sleep(recovery_wait)
  elif attempt == 3:
    logging.warning(f"仍失败，整页 reload 后重试: {op.source_dir}")
    await link_page.page.reload()
    await link_page.page.wait_for_load_state("domcontentloaded")
    await asyncio.sleep(recovery_wait)

  await link_page.goto_path(op.source_dir)
  missing = await _missing_names(link_page, op.names)
  if missing:
    raise BaiduPanError(f"来源列表缺 {missing}")
  await link_page.select_files(op.names)


async def execute_save_plan(link_page: SharedLinkPage,
                            ops: List[SaveOp],
                            dialog: Optional[SaveDialog] = None,
                            pause_seconds: float = 2.0,
                            recovery_wait: float = 1.5,
                            page_factory: Optional[PageFactory] = None) -> List[SaveOpResult]:
  """逐个执行转存操作，单个 op 失败不中断后续，返回全部结果供汇总

  每个 op 的链路：就位+校验+勾选（校验失败逐级恢复）-> 打开保存弹窗 -> 导航目标 -> 确认。
  pause_seconds 是 op 之间的间隔，连续快速转存容易触发风控。

  page_factory 提供时：从第 2 个 op 起每个 op 换新页面（实测同页"转存成功后再
  goto"会确定性挂死——hash 路由不再响应，Escape/reload 都救不回，新开页面必过），
  恢复梯子的末级也用它。编排批量执行时应始终提供。
  """
  if dialog is None:
    dialog = SaveDialog(link_page.page)
  results: List[SaveOpResult] = []

  for i, op in enumerate(ops, 1):
    logging.info(f"save op [{i}/{len(ops)}]: {op.source_dir} -> {op.target_dir} ({len(op.names)} items)")

    if page_factory is not None and i > 1:
      link_page = await _swap_page(link_page, dialog, page_factory)

    prepared = False
    attempts = []
    ladder = (1, 2, 3, 4) if page_factory is not None else (1, 2, 3)
    for attempt in ladder:
      if attempt == 4:
        link_page = await _swap_page(link_page, dialog, page_factory)
        logging.warning(f"三级恢复无效，换新页面最后重试: {op.source_dir}")
      try:
        await _goto_and_select(link_page, op, 1 if attempt == 4 else attempt, recovery_wait)
        prepared = True
        break
      except Exception as e:
        attempts.append(f"尝试{attempt}: {type(e).__name__}: {e}")
        logging.warning(f"op 就位失败（{attempt}/{len(ladder)}）{op.source_dir}: {e}")
    if not prepared:
      results.append(SaveOpResult(op, False, "error: " + "; ".join(attempts)))
      continue

    try:
      await dialog.open()
      nav_ok, nav_msg = await dialog.navigate_to(op.target_dir)
      if not nav_ok:
        results.append(SaveOpResult(op, False, f"navigate failed: {nav_msg}"))
        continue

      confirmed = await dialog.confirm()
      note = "" if confirmed else "confirm 未看到成功提示（可能实际已转存，需人工核对）"
      results.append(SaveOpResult(op, confirmed, note))

    except Exception as e:
      logging.error(f"save op error {op.source_dir}: {e}")
      results.append(SaveOpResult(op, False, f"error: {e}"))

    finally:
      # 弹窗残留会挡住下一个 op 的勾选；确认成功后是否自动关闭未验证过，防御性关掉
      try:
        if await dialog.is_open():
          await dialog.cancel()
      except Exception as e:
        logging.warning(f"close dialog after op failed: {e}")

    if i < len(ops) and pause_seconds > 0:
      await asyncio.sleep(pause_seconds)

  return results


def format_results(results: List[SaveOpResult]) -> str:
  """执行结果的可读汇总，脚本结尾打印"""
  if not results:
    return "(no results)"
  lines: List[str] = []
  for i, r in enumerate(results, 1):
    status = "ok" if r.ok else "FAILED"
    line = f"[{i}] {status}  {r.op.source_dir} -> {r.op.target_dir}  ({len(r.op.names)} items)"
    if r.note:
      line += f"\n      note: {r.note}"
    lines.append(line)
  ok_count = sum(1 for r in results if r.ok)
  lines.append(f"summary: {ok_count}/{len(results)} ok")
  return "\n".join(lines)
