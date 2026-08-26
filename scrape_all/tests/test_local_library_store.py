

import json
import os

from scrape_all.local_library.move import _months, build_plan, execute_plan
from scrape_all.local_library.scan import scan
from scrape_all.local_library.store import LibraryStore
from scrape_all.storage.models import LibraryFolder

# 生产搬运目标目录名（config.LOCAL_LIBRARY_YEJIANG_DIR）：带方括号，
# 不匹配顶层命名规范 -> 根扫描天然跳过它自己，用同名锁死该行为
YJ_DIR = "[yejiang]"
YJ_REL = "[yejiang]"


def make_store(tmp_path):
  return LibraryStore(str(tmp_path / "local_library.db"))


def upsert_a(store, now, month_index=None):
  return store.upsert_folder(
      folder_key="yejiang:A", creator="A", uploader="yejiang",
      original_name="A {25.11} [yejiang]", rel_path="A {25.11} [yejiang]",
      folder_date="2025.11", parse_method="month_flat",
      month_index=month_index or {"2025.01": ["25.01 x"]}, now=now)


def get_row(store, key="yejiang:A"):
  return store.get(key)


def test_upsert_new_then_refresh(tmp_path):
  with make_store(tmp_path) as store:
    assert upsert_a(store, 1000.0) == "new"
    assert upsert_a(store, 2000.0,
                    month_index={"2025.01": ["25.01 x"], "2025.02": ["25.02 y"]}) == "updated"
    row = get_row(store)
    # first_seen 首见不动，last_seen 刷新；月份索引以最新扫描为准
    assert row.first_seen == 1000.0 and row.last_seen == 2000.0
    assert json.loads(row.content_json)["downloaded_months"] == {
        "2025.01": ["25.01 x"], "2025.02": ["25.02 y"]}
    assert row.folder_date == "2025.11"


def test_update_rel_path_keeps_other_fields(tmp_path):
  with make_store(tmp_path) as store:
    upsert_a(store, 1000.0)
    store.update_rel_path("yejiang:A", YJ_REL + "/A", now=3000.0)
    row = get_row(store)
    assert row.rel_path == YJ_REL + "/A"
    assert row.folder_date == "2025.11"          # 搬运不影响 DB 维护的日期
    assert row.original_name == "A {25.11} [yejiang]"
    assert row.last_seen == 3000.0


# ---- scan：假 NAS 树 ----

def make_tree(tmp_path):
  root = tmp_path / "confirmed"
  # 可解析：月份平铺
  (root / "A {25.11} [yejiang]" / "25.01 x").mkdir(parents=True)
  # 工况外：系列夹
  (root / "B {25.09} [yejiang]" / "1.主系列").mkdir(parents=True)
  # 非目标上传者：不碰
  (root / "C {25.10} [hihihiha]" / "whatever").mkdir(parents=True)
  # 脏命名：不碰
  (root / "dd_dd").mkdir(parents=True)
  return root


def test_scan_builds_library(tmp_path):
  root = make_tree(tmp_path)
  with make_store(tmp_path) as store:
    report = scan(str(root), store, yejiang_dir=YJ_DIR, now=1000.0)
    assert report["new"] == 1 and report["updated"] == 0
    assert report["by_method"]["month_flat"] == 1
    assert len(report["out_of_scope"]) == 1
    assert report["out_of_scope"][0][0] == "B {25.09} [yejiang]"
    row = get_row(store)
    assert row.creator == "A" and row.folder_date == "2025.11"
    assert json.loads(row.content_json)["downloaded_months"] == {"2025.01": ["25.01 x"]}
    # 重扫：同库刷新不新增
    report = scan(str(root), store, yejiang_dir=YJ_DIR, now=2000.0)
    assert report["new"] == 0 and report["updated"] == 1


def test_scan_skips_yejiang_dir_itself(tmp_path):
  # [yejiang] 目录名不匹配顶层命名规范，根扫描必须跳过它自身：
  # 不进候选、不进工况外清单、不产生自己的库记录
  root = make_tree(tmp_path)
  (root / YJ_DIR / "somecreator").mkdir(parents=True)
  with make_store(tmp_path) as store:
    report = scan(str(root), store, yejiang_dir=YJ_DIR, now=1000.0)
    assert [n for n, _ in report["out_of_scope"]] == ["B {25.09} [yejiang]"]
    assert report["new"] == 1 and store.get("yejiang:[yejiang]") is None
    # [yejiang] 下的孤儿夹仍要报出来（提醒，不是误扫）
    assert any("无库记录" in a for a in report["anomalies"])


def test_scan_moved_folder_refresh(tmp_path):
  # 搬运后的形态：[yejiang]/A 下刷新月份，folder_date 保持库内值
  root = make_tree(tmp_path)
  with make_store(tmp_path) as store:
    scan(str(root), store, yejiang_dir=YJ_DIR, now=1000.0)
    os.makedirs(root / YJ_DIR)
    os.rename(root / "A {25.11} [yejiang]", root / YJ_DIR / "A")
    store.update_rel_path("yejiang:A", YJ_REL + "/A", now=1500.0)
    (root / YJ_DIR / "A" / "25.02 y").mkdir()
    report = scan(str(root), store, yejiang_dir=YJ_DIR, now=2000.0)
    assert report["updated"] == 1
    row = get_row(store)
    assert row.rel_path == YJ_REL + "/A"
    assert row.folder_date == "2025.11"         # 文件夹名已无日期，靠库维护
    assert row.original_name == "A {25.11} [yejiang]"
    assert json.loads(row.content_json)["downloaded_months"] == {
        "2025.01": ["25.01 x"], "2025.02": ["25.02 y"]}
    # 根目录又冒出同名源（比如人工复制回来）：报告异常不翻转库
    (root / "A {25.11} [yejiang]").mkdir()
    report = scan(str(root), store, yejiang_dir=YJ_DIR, now=3000.0)
    assert report["anomalies"] and "又出现" in report["anomalies"][0]


def test_scan_yejiang_dir_orphan(tmp_path):
  root = make_tree(tmp_path)
  (root / YJ_DIR / "X").mkdir(parents=True)   # 无库记录的孤儿夹（空，解析不了）
  with make_store(tmp_path) as store:
    report = scan(str(root), store, yejiang_dir=YJ_DIR, now=1000.0)
    assert any("无库记录" in a for a in report["anomalies"])
    assert store.get("yejiang:X") is None


def test_scan_yejiang_orphan_parseable_inserts(tmp_path):
  # merge（算法/人工）并进来的新作者：无库记录但可解析 -> 直接入库，
  # folder_date 无日期标记可取，置空（后续靠库维护；orchestrate 不读它）
  root = make_tree(tmp_path)
  (root / YJ_DIR / "X" / "25.03 y").mkdir(parents=True)
  with make_store(tmp_path) as store:
    report = scan(str(root), store, yejiang_dir=YJ_DIR, now=1000.0)
    assert report["new"] == 2            # 根下的 A + yejiang 下的 X
    row = store.get("yejiang:X")
    assert row.creator == "X" and row.folder_date == ""
    assert row.rel_path == YJ_REL + "/X" and row.parse_method == "month_flat"
    assert json.loads(row.content_json)["downloaded_months"] == {"2025.03": ["25.03 y"]}
    # 重扫：变刷新，不重复插入
    report = scan(str(root), store, yejiang_dir=YJ_DIR, now=2000.0)
    assert report["new"] == 0 and report["updated"] == 2
    assert store.get("yejiang:X").last_seen == 2000.0


# ---- move：计划 + 执行 ----

def test_move_months_reads_legacy_and_new_content():
  # 新格式：月份 -> 夹内索引路径
  row = LibraryFolder(folder_key="k",
                      content_json='{"downloaded_months": {"2025.02": ["25.02 x"]}}')
  assert _months(row) == ["2025.02"]
  # 旧格式（重扫重建前的存量记录）：平面月份列表
  row = LibraryFolder(folder_key="k",
                      content_json='{"downloaded_months": ["2024.12", "2025.01"]}')
  assert _months(row) == ["2024.12", "2025.01"]
  # 脏数据兜底
  assert _months(LibraryFolder(folder_key="k", content_json="")) == []

def test_build_plan_and_skip_rules(tmp_path):
  root = make_tree(tmp_path)
  with make_store(tmp_path) as store:
    scan(str(root), store, yejiang_dir=YJ_DIR, now=1000.0)
    items = build_plan(str(root), YJ_DIR, store.all_folders())
    assert len(items) == 1
    it = items[0]
    assert it.action == "move" and it.months_count == 1
    assert it.dst == os.path.join(str(root), YJ_DIR, "A")
    # 目标已存在 -> skip 不覆盖
    os.makedirs(root / YJ_DIR / "A")
    items = build_plan(str(root), YJ_DIR, store.all_folders())
    assert items[0].action == "skip" and "目标已存在" in items[0].reason
    # 库记录已搬运（rel_path 变了）-> skip
    os.rmdir(root / YJ_DIR / "A")
    store.update_rel_path("yejiang:A", YJ_REL + "/A", now=1100.0)
    items = build_plan(str(root), YJ_DIR, store.all_folders())
    assert items[0].action == "skip"


def test_execute_plan_renames_and_updates_db(tmp_path):
  root = make_tree(tmp_path)
  with make_store(tmp_path) as store:
    scan(str(root), store, yejiang_dir=YJ_DIR, now=1000.0)
    items = build_plan(str(root), YJ_DIR, store.all_folders())
    result = execute_plan(items, store, YJ_DIR, now=2000.0)
    assert result["moved"] == 1 and not result["failed"]
    assert not (root / "A {25.11} [yejiang]").exists()
    assert (root / YJ_DIR / "A" / "25.01 x").is_dir()
    row = get_row(store)
    assert row.rel_path == YJ_REL + "/A" and row.last_seen == 2000.0
    # 重跑：已搬的在 plan 阶段变 skip，幂等
    items = build_plan(str(root), YJ_DIR, store.all_folders())
    result = execute_plan(items, store, YJ_DIR, now=3000.0)
    assert result["moved"] == 0 and result["skipped"] == 1
