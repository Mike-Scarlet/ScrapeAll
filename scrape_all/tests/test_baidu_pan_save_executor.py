
import asyncio

from scrape_all.sites.baidu_pan.save_executor import execute_save_plan, format_results
from scrape_all.sites.baidu_pan.save_plan import SaveOp


def make_ops():
  return [
    SaveOp("/Mimu/2025", ["25.08", "25.09"], "/test_save/ver1"),
    SaveOp("/Mimu/2026", ["26.01"], "/test_save/ver1"),
  ]


class FakeEntry:
  def __init__(self, name):
    self.name = name


class FakePage:
  """恢复动作的最小假页：记录 keyboard.press / reload / close"""

  def __init__(self, owner):
    self._owner = owner
    self.calls = []
    self.keyboard = self

  async def press(self, key):
    self.calls.append(("press", key))

  async def reload(self):
    self.calls.append(("reload",))
    self._owner.on_reload()

  async def close(self):
    self.calls.append(("close",))

  async def wait_for_load_state(self, *args, **kwargs):
    pass


class FakeLinkPage:
  def __init__(self, fail_goto=None, listing=None, listing_after_reload=None):
    self.calls = []
    self.fail_goto = fail_goto              # 需要抛异常的 source_dir
    self.listing = list(listing) if listing is not None else ["25.08", "25.09", "26.01"]
    self.listing_after_reload = listing_after_reload   # reload 后切换成的列表（模拟恢复）
    self.page = FakePage(self)

  def on_reload(self):
    if self.listing_after_reload is not None:
      self.listing = self.listing_after_reload

  async def goto_path(self, path):
    self.calls.append(("goto_path", path))
    if path == self.fail_goto:
      raise RuntimeError("goto boom")

  async def list_files(self):
    return [FakeEntry(n) for n in self.listing]

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
  results = run(execute_save_plan(page, make_ops(), dialog=dialog, pause_seconds=0,
                                  recovery_wait=0))

  assert [r.ok for r in results] == [True, True]
  # 每个 op 的链路顺序与参数（校验通过时一次就位，无恢复动作）
  assert page.calls == [
    ("goto_path", "/Mimu/2025"), ("select_files", ("25.08", "25.09")),
    ("goto_path", "/Mimu/2026"), ("select_files", ("26.01",)),
  ]
  assert page.page.calls == []
  assert dialog.calls == [
    ("open",), ("navigate_to", "/test_save/ver1"), ("confirm",),
    ("open",), ("navigate_to", "/test_save/ver1"), ("confirm",),
  ]
  # confirm 后弹窗已关，不需要 cancel
  assert ("cancel",) not in dialog.calls


def test_navigate_failure_cancels_and_continues():
  page, dialog = FakeLinkPage(), FakeDialog(nav_fail_at={"/test_save/ver1"})
  results = run(execute_save_plan(page, make_ops(), dialog=dialog, pause_seconds=0,
                                  recovery_wait=0))

  assert [r.ok for r in results] == [False, False]
  assert "navigate failed" in results[0].note
  # 导航失败后弹窗要被 cancel 关掉，且第二个 op 照常执行
  assert ("cancel",) in dialog.calls
  assert ("confirm",) not in dialog.calls
  assert len(page.calls) == 4


def test_confirm_false_marks_failed_with_note():
  dialog = FakeDialog(confirm_results=[False])
  results = run(execute_save_plan(FakeLinkPage(), make_ops(), dialog=dialog, pause_seconds=0,
                                  recovery_wait=0))

  assert results[0].ok is False and "需人工核对" in results[0].note
  assert results[1].ok is True


def test_goto_error_continues_to_next_op():
  page = FakeLinkPage(fail_goto="/Mimu/2025")
  dialog = FakeDialog()
  results = run(execute_save_plan(page, make_ops(), dialog=dialog, pause_seconds=0,
                                  recovery_wait=0))

  assert [r.ok for r in results] == [False, True]
  assert "error" in results[0].note
  # goto 每次都炸：三级尝试都走过（Escape + reload 都动用了）才放弃
  gotos = [c for c in page.calls if c[0] == "goto_path"]
  assert len(gotos) == 3 + 1   # 第一个 op 三次 + 第二个 op 一次
  assert ("press", "Escape") in page.page.calls
  assert ("reload",) in page.page.calls


def test_stale_listing_recovers_via_reload():
  # 模拟真跑事故形态：hash 跳转后内容停在旧目录（列表缺名字），reload 后恢复
  page = FakeLinkPage(listing=[], listing_after_reload=["26.01"])
  dialog = FakeDialog()
  results = run(execute_save_plan(page, make_ops()[1:], dialog=dialog, pause_seconds=0,
                                  recovery_wait=0))

  assert [r.ok for r in results] == [True]
  # 尝试1 校验失败 -> 尝试2 Escape 后仍缺 -> 尝试3 reload 后列表正确 -> 勾选成功
  assert ("press", "Escape") in page.page.calls
  assert ("reload",) in page.page.calls
  select = [c for c in page.calls if c[0] == "select_files"]
  assert select == [("select_files", ("26.01",))]


def test_missing_names_fails_op_with_attempts_note():
  page = FakeLinkPage(listing=["别的名字.mp4"])
  dialog = FakeDialog()
  results = run(execute_save_plan(page, make_ops()[1:], dialog=dialog, pause_seconds=0,
                                  recovery_wait=0))

  assert [r.ok for r in results] == [False]
  assert "error" in results[0].note and "尝试3" in results[0].note
  assert "来源列表缺" in results[0].note
  # 三级都试过仍失败，绝不勾选、不碰弹窗
  assert ("select_files", ("26.01",)) not in page.calls
  assert dialog.calls == []


def test_dialog_left_open_after_confirm_gets_cancelled():
  dialog = FakeDialog(stay_open_after_confirm=True)
  results = run(execute_save_plan(FakeLinkPage(), make_ops()[:1], dialog=dialog, pause_seconds=0,
                                  recovery_wait=0))

  assert results[0].ok is True
  assert ("cancel",) in dialog.calls


def make_factory(created, listing=None):
  async def factory():
    page = FakeLinkPage(listing=list(listing) if listing is not None else None)
    created.append(page)
    return page
  return factory


def test_page_factory_swaps_page_per_op():
  # 提供 factory 时：第 2 个 op 起换新页面（同页"保存后再 goto"实测会挂死）
  created = []
  factory = make_factory(created)
  page1 = FakeLinkPage()
  dialog = FakeDialog()
  results = run(execute_save_plan(page1, make_ops(), dialog=dialog, pause_seconds=0,
                                  recovery_wait=0, page_factory=factory))

  assert [r.ok for r in results] == [True, True]
  assert len(created) == 1                       # 只有 op2 开了新页
  assert page1.calls == [("goto_path", "/Mimu/2025"), ("select_files", ("25.08", "25.09"))]
  assert created[0].calls == [("goto_path", "/Mimu/2026"), ("select_files", ("26.01",))]
  assert ("close",) in page1.page.calls          # 旧页被关掉
  assert dialog.page is created[0].page          # 弹窗换绑到新页


def test_attempt4_fresh_page_is_last_resort():
  # 三级恢复全灭后，第 4 级换新页面救回（首个页面列表永远缺名字）
  created = []
  factory = make_factory(created, listing=["25.08", "25.09", "26.01"])
  page1 = FakeLinkPage(listing=[])
  dialog = FakeDialog()
  results = run(execute_save_plan(page1, make_ops()[:1], dialog=dialog, pause_seconds=0,
                                  recovery_wait=0, page_factory=factory))

  assert [r.ok for r in results] == [True]
  assert len(created) == 1
  # 前三级（普通/Escape/reload）都动用过，第 4 级新页上完成勾选
  assert ("press", "Escape") in page1.page.calls and ("reload",) in page1.page.calls
  assert created[0].calls == [("goto_path", "/Mimu/2025"), ("select_files", ("25.08", "25.09"))]


def test_format_results_summary():
  dialog = FakeDialog(confirm_results=[False])
  results = run(execute_save_plan(FakeLinkPage(), make_ops(), dialog=dialog, pause_seconds=0,
                                  recovery_wait=0))
  text = format_results(results)
  assert "FAILED" in text and "[2] ok" in text
  assert "summary: 1/2 ok" in text
