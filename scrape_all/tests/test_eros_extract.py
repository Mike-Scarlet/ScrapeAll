import io
import json
import os
import time
import zipfile

import pytest

from scrape_all.sites.eroscripts.extract import (
    EX_DONE, EX_FAILED, ArchiveExtractor, classify_parts, extract_zip_file,
    resolve_target_dir,
)
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroExtract, EroLink

TOPIC = 308104


def make_store(tmp_path):
  return TopicStore(str(tmp_path / "ero.db"))


def add_erolink(store, rel, tid=TOPIC, url=None):
  store.db.InsertRecord(EroLink(
      url=url or f"https://pixeldrain.com/l/{rel}", host="pixeldrain.com",
      kind="media", dl_status="downloaded", dl_path=rel,
      dl_size=1, first_topic_id=tid))
  store.db.Commit()


def build_zip(path, entries: dict):
  with zipfile.ZipFile(path, "w") as z:
    for name, data in entries.items():
      z.writestr(name, data)


def zip_bytes(entries: dict) -> bytes:
  buf = io.BytesIO()
  with zipfile.ZipFile(buf, "w") as z:
    for name, data in entries.items():
      z.writestr(name, data)
  return buf.getvalue()


def rows_by_path(store):
  return {r.archive_path: r
          for r in store.db.QueryRecords(EroExtract)}


@pytest.fixture
def env(tmp_path):
  root = tmp_path / "scrape"
  (root / str(TOPIC)).mkdir(parents=True)
  store = make_store(tmp_path)
  return root, store


def run_ex(root, store, **kw):
  lines = []
  ex = ArchiveExtractor(store, str(root), emit=lines.append, **kw)
  return ex.run(), lines


# ---- 纯函数 ----

def test_classify_parts_junk_and_slip():
  assert classify_parts("__MACOSX/._foo")[1] == "junk"
  assert classify_parts("a/.DS_Store")[1] == "junk"
  assert classify_parts("../evil.txt")[1] == "slip"
  assert classify_parts("a\\..\\b.txt")[1] == "slip"
  parts, disp = classify_parts("sub/a<b>.mp4")
  assert disp == "file" and parts == ["sub", "a_b_.mp4"]


def test_resolve_target_dir_suffixes_on_file_collision(tmp_path):
  base = tmp_path
  (base / "pack").write_bytes(b"i am a file not a dir")
  assert resolve_target_dir(str(base / "pack.zip")) == str(base / "pack.2")
  (base / "pack.2").write_bytes(b"also file")
  assert resolve_target_dir(str(base / "pack.zip")) == str(base / "pack.3")
  # 目录已在（半成品重跑）直接复用
  (base / "other").mkdir()
  assert resolve_target_dir(str(base / "other.zip")) == str(base / "other")


# ---- zip 主链路 ----

def test_zip_extracts_to_stem_dir_with_structure(env):
  root, store = env
  zp = root / str(TOPIC) / "pack.zip"
  build_zip(zp, {"v.mp4": b"12345", "v.funscript": b"{}",
                 "sub/extra.mp4": b"x" * 10})
  add_erolink(store, f"{TOPIC}/pack.zip")
  totals, _ = run_ex(root, store)
  assert totals["extracted"] == 1 and totals["failed"] == 0
  d = root / str(TOPIC) / "pack"
  assert (d / "v.mp4").read_bytes() == b"12345"
  assert (d / "sub" / "extra.mp4").read_bytes() == b"x" * 10
  row = rows_by_path(store)[f"{TOPIC}/pack.zip"]
  assert row.status == EX_DONE and row.depth == 1 and row.topic_id == TOPIC
  assert row.parent_path == "" and row.note == ""
  files = json.loads(row.files_json)
  assert {f["src"] for f in files} == {"v.mp4", "v.funscript", "sub/extra.mp4"}
  assert all(f["action"] == "wrote" for f in files)


def test_rerun_done_skip_preserves_mtime(env):
  root, store = env
  zp = root / str(TOPIC) / "pack.zip"
  build_zip(zp, {"v.mp4": b"12345"})
  add_erolink(store, f"{TOPIC}/pack.zip")
  run_ex(root, store)
  placed = root / str(TOPIC) / "pack" / "v.mp4"
  old = time.time() - 5000
  os.utime(placed, (old, old))
  totals, _ = run_ex(root, store)
  assert totals["extracted"] == 0 and totals["done_skip"] == 1
  assert os.path.getmtime(placed) == old


def test_corrupt_zip_fails_and_retries(env):
  root, store = env
  zp = root / str(TOPIC) / "bad.zip"
  zp.write_bytes(b"this is not a zip at all")
  add_erolink(store, f"{TOPIC}/bad.zip")
  totals, _ = run_ex(root, store)
  assert totals["failed"] == 1 and totals["extracted"] == 0
  assert rows_by_path(store)[f"{TOPIC}/bad.zip"].status == EX_FAILED
  # failed 行不挡重跑：再跑一次还是失败（继续留在重试队列里）
  totals2, _ = run_ex(root, store)
  assert totals2["failed"] == 1 and totals2["extracted"] == 0


def test_junk_entries_skipped(env):
  root, store = env
  zp = root / str(TOPIC) / "pack.zip"
  build_zip(zp, {"__MACOSX/._v.mp4": b"junk", ".DS_Store": b"junk",
                 "Thumbs.db": b"junk", "v.mp4": b"12345"})
  add_erolink(store, f"{TOPIC}/pack.zip")
  totals, _ = run_ex(root, store)
  assert totals["extracted"] == 1
  d = root / str(TOPIC) / "pack"
  assert list(d.rglob("*")) and not (d / ".DS_Store").exists()
  files = json.loads(rows_by_path(store)[f"{TOPIC}/pack.zip"].files_json)
  assert [f["src"] for f in files] == ["v.mp4"]


def test_zip_slip_fails_whole_archive(env):
  root, store = env
  zp = root / str(TOPIC) / "evil.zip"
  build_zip(zp, {"../evil.txt": b"bad", "ok.mp4": b"12345"})
  add_erolink(store, f"{TOPIC}/evil.zip")
  totals, _ = run_ex(root, store)
  assert totals["failed"] == 1
  assert not (root / str(TOPIC) / "evil.txt").exists()
  # 整包失败：ok.mp4 也一并作废（不落 done）
  assert not (root / str(TOPIC) / "evil" / "ok.mp4").exists()


def test_long_path_fails(env):
  root, store = env
  zp = root / str(TOPIC) / "deep.zip"
  seg = "x" * 120
  build_zip(zp, {f"{seg}/{seg}/{seg}.txt": b"data"})
  add_erolink(store, f"{TOPIC}/deep.zip")
  totals, _ = run_ex(root, store)
  assert totals["failed"] == 1
  assert "超长" in rows_by_path(store)[f"{TOPIC}/deep.zip"].note


def test_existing_same_size_skipped_diff_size_token(env):
  root, store = env
  zp = root / str(TOPIC) / "pack.zip"
  build_zip(zp, {"same.mp4": b"12345", "diff.mp4": b"abc"})
  d = root / str(TOPIC) / "pack"
  d.mkdir()
  (d / "same.mp4").write_bytes(b"12345")     # 上次 failed 的半成品：同体积
  old = time.time() - 5000
  os.utime(d / "same.mp4", (old, old))
  (d / "diff.mp4").write_bytes(b"zzzz")      # 异体积撞名：不覆盖，落第二把
  add_erolink(store, f"{TOPIC}/pack.zip")
  totals, _ = run_ex(root, store)
  assert totals["extracted"] == 1
  assert (d / "same.mp4").read_bytes() == b"12345"
  assert os.path.getmtime(d / "same.mp4") == old
  assert (d / "diff.mp4").read_bytes() == b"zzzz"       # 原文件保住
  second = [p for p in d.iterdir()
            if p.name != "diff.mp4" and p.name.startswith("diff.")]
  assert len(second) == 1 and second[0].read_bytes() == b"abc"
  files = json.loads(rows_by_path(store)[f"{TOPIC}/pack.zip"].files_json)
  by_src = {f["src"]: f for f in files}
  assert by_src["same.mp4"]["action"] == "have"
  assert by_src["diff.mp4"]["action"] == "wrote"
  assert by_src["diff.mp4"]["path"].endswith(".mp4") and "diff." in by_src["diff.mp4"]["path"]


# ---- 范围控制 ----

def test_top_level_without_erolink_skipped(env):
  root, store = env
  build_zip(root / str(TOPIC) / "noref.zip", {"v.mp4": b"12345"})
  totals, _ = run_ex(root, store)
  assert totals["no_db"] == 1 and totals["extracted"] == 0
  assert f"{TOPIC}/noref.zip" not in rows_by_path(store)
  assert not (root / str(TOPIC) / "noref").exists()


def test_root_level_archive_deferred(env):
  root, store = env
  build_zip(root / "loose.zip", {"v.mp4": b"12345"})
  add_erolink(store, "loose.zip", tid=TOPIC)
  totals, _ = run_ex(root, store)
  assert totals["deferred"] == 1 and totals["extracted"] == 0


# ---- 嵌套递归 ----

def test_nested_zip_recursion_depth_parent(env):
  root, store = env
  inner = zip_bytes({"in.funscript": b"{}"})
  build_zip(root / str(TOPIC) / "outer.zip", {"inner.zip": inner})
  add_erolink(store, f"{TOPIC}/outer.zip")
  totals, _ = run_ex(root, store)
  assert totals["extracted"] == 2 and totals["passes"] == 2
  assert (root / str(TOPIC) / "outer" / "inner.zip").is_file()
  assert (root / str(TOPIC) / "outer" / "inner" / "in.funscript").is_file()
  rows = rows_by_path(store)
  assert rows[f"{TOPIC}/outer.zip"].depth == 1
  inner_row = rows[f"{TOPIC}/outer/inner.zip"]
  assert inner_row.status == EX_DONE and inner_row.depth == 2
  assert inner_row.parent_path == f"{TOPIC}/outer.zip"
  assert inner_row.topic_id == TOPIC


def test_nested_depth_cap_marks_failed(env):
  root, store = env
  l4 = zip_bytes({"deep.txt": b"x"})
  l3 = zip_bytes({"L4.zip": l4})
  l2 = zip_bytes({"L3.zip": l3})
  build_zip(root / str(TOPIC) / "L1.zip", {"L2.zip": l2})
  add_erolink(store, f"{TOPIC}/L1.zip")
  totals, _ = run_ex(root, store)
  assert totals["extracted"] == 3 and totals["failed"] == 1
  rows = rows_by_path(store)
  assert rows[f"{TOPIC}/L1.zip"].depth == 1
  assert rows[f"{TOPIC}/L1/L2.zip"].depth == 2
  assert rows[f"{TOPIC}/L1/L2/L3.zip"].depth == 3
  deepest = rows[f"{TOPIC}/L1/L2/L3/L4.zip"]
  assert deepest.status == EX_FAILED and "深度" in deepest.note
  # 第 4 层的包体留在原地，不展开
  assert (root / str(TOPIC) / "L1" / "L2" / "L3" / "L4.zip").is_file()
  assert not (root / str(TOPIC) / "L1" / "L2" / "L3" / "L4").exists()


# ---- rar（注入 fake runner） ----

def fake_rar(files: dict):
  def run(args, timeout):
    dest = args[-1].rstrip("\\/")
    os.makedirs(dest, exist_ok=True)
    for name, data in files.items():
      p = os.path.join(dest, *name.split("/"))
      os.makedirs(os.path.dirname(p), exist_ok=True)
      with open(p, "wb") as f:
        f.write(data)
    return 0, ""
  return run


def test_rar_extract_sanitized_via_runner(env):
  root, store = env
  rar = root / str(TOPIC) / "vid.rar"
  rar.write_bytes(b"fake rar bytes")
  add_erolink(store, f"{TOPIC}/vid.rar")
  # 名字里的双空格 Windows 合法（fake 得能落盘）但 sanitize 会折叠成单空格，
  # 借此验证 rar 链路真的过了一遍清洗；<> 等硬非法字符的清洗在 zip 测试覆盖
  totals, _ = run_ex(root, store, run_rar=fake_rar({"a  b.mp4": b"12345"}))
  assert totals["extracted"] == 1
  assert (root / str(TOPIC) / "vid" / "a b.mp4").read_bytes() == b"12345"
  # unrar 的临时目录已清
  assert not [p for p in (root / str(TOPIC)).iterdir() if p.name.startswith(".unrar.")]
  row = rows_by_path(store)[f"{TOPIC}/vid.rar"]
  assert row.status == EX_DONE
  assert json.loads(row.files_json)[0]["src"] == "a  b.mp4"


def test_rar_nonzero_exit_fails(env):
  root, store = env
  rar = root / str(TOPIC) / "bad.rar"
  rar.write_bytes(b"fake rar bytes")
  add_erolink(store, f"{TOPIC}/bad.rar")
  def run(args, timeout):
    return 11, "wrong password"
  totals, _ = run_ex(root, store, run_rar=run)
  assert totals["failed"] == 1
  assert "退出码 11" in rows_by_path(store)[f"{TOPIC}/bad.rar"].note
  assert "加密" not in rows_by_path(store)[f"{TOPIC}/bad.rar"].note


def test_rar_password_eof_hint(env):
  """255 = 密码提示吃 EOF：note 带加密提示（真跑遇到的两个加密 rar）"""
  root, store = env
  rar = root / str(TOPIC) / "enc.rar"
  rar.write_bytes(b"fake rar bytes")
  add_erolink(store, f"{TOPIC}/enc.rar")
  def run(args, timeout):
    return 255, ""
  totals, _ = run_ex(root, store, run_rar=run)
  assert totals["failed"] == 1
  note = rows_by_path(store)[f"{TOPIC}/enc.rar"].note
  assert "退出码 255" in note and "加密" in note


# ---- 7z 工具缺口 ----

def test_7z_unsupported_fails_with_note(env):
  root, store = env
  zp = root / str(TOPIC) / "pack.7z"
  zp.write_bytes(b"fake 7z")
  add_erolink(store, f"{TOPIC}/pack.7z")
  totals, _ = run_ex(root, store)
  assert totals["failed"] == 1
  assert "人工" in rows_by_path(store)[f"{TOPIC}/pack.7z"].note
