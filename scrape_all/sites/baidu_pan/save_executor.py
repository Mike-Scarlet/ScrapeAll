
import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional

from scrape_all.sites.baidu_pan.pages.save_dialog import SaveDialog
from scrape_all.sites.baidu_pan.pages.shared_link_page import SharedLinkPage
from scrape_all.sites.baidu_pan.save_plan import SaveOp

# 执行器：按计划逐个做"勾选 + 转存"。计划本身（build_save_plan）已人工确认过。


@dataclass
class SaveOpResult:
  op: SaveOp
  ok: bool
  note: str = ""      # 失败/不确定时的补充说明


async def execute_save_plan(link_page: SharedLinkPage,
                            ops: List[SaveOp],
                            dialog: Optional[SaveDialog] = None,
                            pause_seconds: float = 2.0) -> List[SaveOpResult]:
  """逐个执行转存操作，单个 op 失败不中断后续，返回全部结果供汇总

  每个 op 的链路：goto 来源目录 -> 按名勾选 -> 打开保存弹窗 -> 导航目标 -> 确认。
  pause_seconds 是 op 之间的间隔，连续快速转存容易触发风控。
  """
  if dialog is None:
    dialog = SaveDialog(link_page.page)
  results: List[SaveOpResult] = []

  for i, op in enumerate(ops, 1):
    logging.info(f"save op [{i}/{len(ops)}]: {op.source_dir} -> {op.target_dir} ({len(op.names)} items)")
    try:
      await link_page.goto_path(op.source_dir)
      await link_page.select_files(op.names)

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
