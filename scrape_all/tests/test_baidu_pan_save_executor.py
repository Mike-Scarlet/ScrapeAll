
import asyncio

from scrape_all.sites.baidu_pan.save_executor import execute_save_plan, format_results
from scrape_all.sites.baidu_pan.save_plan import SaveOp


def make_ops():
  return [
    SaveOp("/Mimu/2025", ["25.08", "25.09"], "/test_save/ver1"),
    SaveOp("/Mimu/2026", ["26.01"], "/test_save/ver1"),
  ]


class FakeLinkPage:
  def __init__(self, fail_goto=None):
    self.calls = []
    self.fail_goto = fail_goto        # 需要抛异常的 source_dir

  async def goto_path(self, path):
    self.calls.append(("goto_path", path))
    if path == self.fail_goto:
      raise RuntimeError("goto boom")

  async def select_files(self, names):
    self.calls.append(("select_files", tuple(names)))


class FakeDialog:
  def __init__(self, nav_fail_at=(), confirm_results=None, stay_open_after_confirm=False):
    self.calls = []
    self.nav_fail_at = set(nav_fail_at)          # navigate_to 返回失败的 target
    self.confirm_results = list(confirm_results or [])
    self.stay_open_after_confirm = stay_open_after_confirm
    self._open = False

  async def is_open(self):
    return self._open

  async def open(self):
    self.calls.append(("open",))
    self._open = True

  async def navigate_to(self, path, create_if_missing=True):
    self.calls.append(("navigate_to", path))
    if path in self.nav_fail_at:
      return False, "路径不存在"
    return True, "ok"

  async def confirm(self):
    self.calls.append(("confirm",))
    self._open = self.stay_open_after_confirm
    return self.confirm_results.pop(0) if self.confirm_results else True

  async def cancel(self):
    self.calls.append(("cancel",))
    self._open = False


def run(coro):
  return asyncio.run(coro)


def test_happy_path_order_and_args():
  page, dialog = FakeLinkPage(), FakeDialog()
  results = run(execute_save_plan(page, make_ops(), dialog=dialog, pause_seconds=0))

  assert [r.ok for r in results] == [True, True]
  # 每个 op 的链路顺序与参数
  assert page.calls == [
    ("goto_path", "/Mimu/2025"), ("select_files", ("25.08", "25.09")),
    ("goto_path", "/Mimu/2026"), ("select_files", ("26.01",)),
  ]
  assert dialog.calls == [
    ("open",), ("navigate_to", "/test_save/ver1"), ("confirm",),
    ("open",), ("navigate_to", "/test_save/ver1"), ("confirm",),
  ]
  # confirm 后弹窗已关，不需要 cancel
  assert ("cancel",) not in dialog.calls


def test_navigate_failure_cancels_and_continues():
  page, dialog = FakeLinkPage(), FakeDialog(nav_fail_at={"/test_save/ver1"})
  results = run(execute_save_plan(page, make_ops(), dialog=dialog, pause_seconds=0))

  assert [r.ok for r in results] == [False, False]
  assert "navigate failed" in results[0].note
  # 导航失败后弹窗要被 cancel 关掉，且第二个 op 照常执行
  assert ("cancel",) in dialog.calls
  assert ("confirm",) not in dialog.calls
  assert len(page.calls) == 4


def test_confirm_false_marks_failed_with_note():
  dialog = FakeDialog(confirm_results=[False])
  results = run(execute_save_plan(FakeLinkPage(), make_ops(), dialog=dialog, pause_seconds=0))

  assert results[0].ok is False and "需人工核对" in results[0].note
  assert results[1].ok is True


def test_goto_error_continues_to_next_op():
  page = FakeLinkPage(fail_goto="/Mimu/2025")
  dialog = FakeDialog()
  results = run(execute_save_plan(page, make_ops(), dialog=dialog, pause_seconds=0))

  assert [r.ok for r in results] == [False, True]
  assert "error" in results[0].note


def test_dialog_left_open_after_confirm_gets_cancelled():
  dialog = FakeDialog(stay_open_after_confirm=True)
  results = run(execute_save_plan(FakeLinkPage(), make_ops()[:1], dialog=dialog, pause_seconds=0))

  assert results[0].ok is True
  assert ("cancel",) in dialog.calls


def test_format_results_summary():
  dialog = FakeDialog(confirm_results=[False])
  results = run(execute_save_plan(FakeLinkPage(), make_ops(), dialog=dialog, pause_seconds=0))
  text = format_results(results)
  assert "FAILED" in text and "[2] ok" in text
  assert "summary: 1/2 ok" in text
