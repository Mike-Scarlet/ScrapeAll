
"""extract 阶段编排核心：J:\\es_scrape 上的档案（zip/rar）解到包同名子目录，
供配对决策表消费。纯本地零流量。

- 布局：<dest_root>/<topic>/<包stem>/，保留包内目录结构；包文件保留不删
  （dl_path 引用完整性）。stem 撞一个同名【文件】时序号后缀目录。
- 范围：顶层档案（直接躺在 topic 目录下）须有 EroLink downloaded 行引用
  （dl_path 对得上），否则跳过报"无库引用"；包内嵌套档案（解出来才发现）
  不需要库行，递归解到不动点，深度上限 EXTRACT_DEPTH_MAX。
- 幂等：EroExtract（archive_path 主键）done 跳过；failed 重跑续传——逐条目
  体积比对，已在且同体积不重写；无行才整包处理。
- 安全：包内路径逐段 sanitize_filename；.. 段整包失败；撞名（已在且体积不同）
  token 第二把（与 downloader 同哲学，防静默覆盖）；目标路径超长整包失败；
  __MACOSX/.DS_Store/Thumbs.db/desktop.ini 跳过；加密/损坏整包失败。
- rar：unrar 子进程解到临时目录再按清洗路径搬入（unrar 只会写原名，绕开它
  才能统一走 sanitize），退出码非 0 判失败。

CLI 在 scripts/extract_archives.py；本模块只依赖注入 store / run_rar，
全部逻辑可离线单测。
"""

import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import Callable

from scrape_all.downloader.fsutil import sanitize_filename, url_token
from scrape_all.sites.eroscripts.history import to_iso
from scrape_all.storage.models import EroExtract, EroLink

EXTRACT_DEPTH_MAX = 3
ARCHIVE_EXTS = {".zip", ".rar", ".7z"}
MAX_DEST_LEN = 250          # Windows MAX_PATH 260 留余量
JUNK_TOPDIRS = {"__macosx"}
JUNK_BASENAMES = {".ds_store", "thumbs.db", "desktop.ini"}
VIDEO_EXT = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".m4v",
             ".mpg", ".mpeg", ".ts", ".flv"}
SCRIPT_EXT = {".funscript", ".lua"}

UNRAR_EXE = r"E:\Program Files\unrar\UnRAR.exe"
UNRAR_TIMEOUT_S = 900.0

EX_DONE, EX_FAILED = "done", "failed"


class ExtractError(RuntimeError):
  """语义性失败（危险路径/超长/无工具/解压核验不过），整包 failed 落库"""


def _now_iso() -> str:
  return to_iso(datetime.now(timezone.utc).replace(tzinfo=None))


def _rel_from_root(dest_root: str, abs_path: str) -> str:
  """相对根、统一 '/'（与 EroLink.dl_path / EroExtract 同风格）"""
  return os.path.relpath(abs_path, dest_root).replace(os.sep, "/")


def classify_parts(inner: str) -> tuple[list[str], str]:
  """包内条目路径 -> (清洗后路径段, 处置)。处置：file / junk / slip。
  目录条目（尾 /）由调用方先过滤，这里只看文件条目。"""
  parts = [p for p in re.split(r"[/\\]+", inner) if p not in ("", ".")]
  if not parts or any(p == ".." for p in parts):
    return [], "slip"
  if parts[0].lower() in JUNK_TOPDIRS or parts[-1].lower() in JUNK_BASENAMES:
    return [], "junk"
  return [sanitize_filename(p) for p in parts], "file"


def resolve_target_dir(archive_abs: str) -> str:
  """包旁同名子目录。目录已在（上次 failed 的半成品 / 人工建过）直接复用
  ——条目级体积比对会兜住；被一个同名【文件】占着才序号后缀。"""
  base = os.path.dirname(archive_abs)
  stem = os.path.splitext(os.path.basename(archive_abs))[0]
  target = os.path.join(base, stem)
  n = 2
  while os.path.isfile(target):
    target = os.path.join(base, f"{stem}.{n}")
    n += 1
  return target


def resolve_extract_dest(target_dir: str, parts: list[str],
                         size: int) -> tuple[str, str]:
  """条目落点：不在 -> 写；在且同体积 -> have（幂等跳过）；在但体积不同 ->
  token 第二把（同 key 同内容，第二把已在且同体积也算 have）。返回
  (abs路径, 'write'|'have')。"""
  dest = os.path.join(target_dir, *parts)
  if not os.path.exists(dest):
    return dest, "write"
  if os.path.getsize(dest) == size:
    return dest, "have"
  key = "/".join(parts)
  stem, ext = os.path.splitext(dest)
  alt = f"{stem}.{url_token(key)}{ext}"
  n = 2
  while os.path.exists(alt) and os.path.getsize(alt) != size:
    alt = f"{stem}.{url_token(key)}.{n}{ext}"
    n += 1
  return alt, "write" if not os.path.exists(alt) else "have"


def extract_zip_file(archive_abs: str, dest_root: str
                     ) -> tuple[list[dict], int]:
  """单 zip 解到 resolve_target_dir。返回 (files_json 条目, 新写字节数)；
  失败抛 ExtractError（含加密/损坏——zipfile 的 RuntimeError/BadZipFile
  归并到这）。每写一个条目即核验体积，全部条目落位后才算数。"""
  target = resolve_target_dir(archive_abs)
  os.makedirs(target, exist_ok=True)
  files, wrote, seen = [], 0, set()
  try:
    with zipfile.ZipFile(archive_abs) as z:
      for info in z.infolist():
        if info.is_dir():
          continue
        parts, disp = classify_parts(info.filename)
        if disp == "junk":
          continue
        if disp == "slip":
          raise ExtractError(f"危险路径条目: {info.filename!r}")
        dest, action = resolve_extract_dest(target, parts, info.file_size)
        if dest in seen:   # 同包内重名条目：第二个直接走第二把，不吃掉内容
          key = "/".join(parts)
          stem, ext = os.path.splitext(dest)
          dest = f"{stem}.{url_token(key)}{ext}"
          action = "write"
        if len(dest) > MAX_DEST_LEN:
          raise ExtractError(f"目标路径超长({len(dest)}): {dest}")
        if action == "write":
          os.makedirs(os.path.dirname(dest), exist_ok=True)
          with z.open(info) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
          wrote += info.file_size
        seen.add(dest)
        files.append({"path": _rel_from_root(dest_root, dest),
                      "size": info.file_size, "src": info.filename,
                      "action": "wrote" if action == "write" else "have"})
  except ExtractError:
    raise
  except RuntimeError as e:      # zipfile 加密条目的报错形态
    raise ExtractError(f"加密或损坏: {e}") from e
  except zipfile.BadZipFile as e:
    raise ExtractError(f"zip 损坏: {e}") from e
  _verify_files(files, dest_root)
  return files, wrote


def extract_rar_file(archive_abs: str, dest_root: str,
                     run_rar: Callable[[list[str], float], tuple[int, str]]
                     ) -> tuple[list[dict], int]:
  """单 rar：unrar 解到临时目录（写原名），再逐文件按清洗路径搬入 target。
  返回同 zip。unrar 只信退出码；体积核验与 zip 一致。"""
  base = os.path.dirname(archive_abs)
  target = resolve_target_dir(archive_abs)
  os.makedirs(target, exist_ok=True)
  tmp = tempfile.mkdtemp(prefix=".unrar.", dir=base)
  try:
    rc, _ = run_rar(["x", "-idq", "-o+", archive_abs, tmp + os.sep],
                    UNRAR_TIMEOUT_S)
    if rc != 0:
      # 255 = 密码提示吃 EOF（本管线 stdin=DEVNULL，加密 rar 必现）
      hint = "（多半加密需密码，帖文 Pass/pw 提示找）" if rc == 255 else ""
      raise ExtractError(f"unrar 退出码 {rc}{hint}")
    files, wrote, seen = [], 0, set()
    for dirpath, _dn, fns in os.walk(tmp):
      for fn in fns:
        src = os.path.join(dirpath, fn)
        inner = os.path.relpath(src, tmp)
        parts, disp = classify_parts(inner)
        if disp == "junk":
          os.remove(src)
          continue
        if disp == "slip":
          raise ExtractError(f"危险路径条目: {inner!r}")
        size = os.path.getsize(src)
        dest, action = resolve_extract_dest(target, parts, size)
        if dest in seen:
          key = "/".join(parts)
          stem, ext = os.path.splitext(dest)
          dest = f"{stem}.{url_token(key)}{ext}"
          action = "write"
        if len(dest) > MAX_DEST_LEN:
          raise ExtractError(f"目标路径超长({len(dest)}): {dest}")
        if action == "write":
          os.makedirs(os.path.dirname(dest), exist_ok=True)
          shutil.move(src, dest)
          wrote += size
        else:
          os.remove(src)
        seen.add(dest)
        files.append({"path": _rel_from_root(dest_root, dest), "size": size,
                      "src": inner.replace(os.sep, "/"),
                      "action": "wrote" if action == "write" else "have"})
    _verify_files(files, dest_root)
    return files, wrote
  finally:
    shutil.rmtree(tmp, ignore_errors=True)


def _verify_files(files: list[dict], dest_root: str):
  """落位核验：每个记录条目都在盘上且体积精确对上（rar 的 size 来自盘，
  zip 的来自目录项——都对得上才算 done，防半成品被标完成）。"""
  for f in files:
    p = os.path.join(dest_root, *f["path"].split("/"))
    if not os.path.isfile(p) or os.path.getsize(p) != f["size"]:
      raise ExtractError(f"核验缺件: {f['path']}")


def zip_preview(archive_abs: str) -> dict:
  """dry-run 用：zip 条目类型清点（只读目录项不解数据）"""
  out = {"entries": 0, "video": 0, "script": 0, "archive": 0, "other": 0,
         "junk": 0, "uncompressed": 0, "err": None}
  try:
    with zipfile.ZipFile(archive_abs) as z:
      for info in z.infolist():
        if info.is_dir():
          continue
        parts, disp = classify_parts(info.filename)
        if disp == "junk":
          out["junk"] += 1
          continue
        out["entries"] += 1
        out["uncompressed"] += info.file_size
        ext = os.path.splitext(parts[-1])[1].lower()
        if ext in VIDEO_EXT:
          out["video"] += 1
        elif ext in SCRIPT_EXT:
          out["script"] += 1
        elif ext in ARCHIVE_EXTS:
          out["archive"] += 1
        else:
          out["other"] += 1
  except Exception as e:
    out["err"] = f"{type(e).__name__}: {e}"
  return out


def scan_archives(dest_root: str) -> list[dict]:
  """盘上档案清点：[{abs, rel('/' 风格), size}]，rel 排序稳定"""
  out = []
  for dirpath, _dn, fns in os.walk(dest_root):
    for fn in fns:
      if os.path.splitext(fn)[1].lower() not in ARCHIVE_EXTS:
        continue
      p = os.path.join(dirpath, fn)
      try:
        sz = os.path.getsize(p)
      except OSError:
        continue
      out.append({"abs": p, "rel": _rel_from_root(dest_root, p), "size": sz})
  out.sort(key=lambda a: a["rel"])
  return out


class ArchiveExtractor:
  """编排：scan -> plan（幂等分类 + 深度/父级推导）-> 逐包解 -> 落库，
  多 pass 跑到不动点（pass N 解出的嵌套档案 pass N+1 接手）。"""

  def __init__(self, store, dest_root: str,
               emit: Callable[[str], None] = print,
               run_rar: Callable[[list[str], float], tuple[int, str]] = None):
    self.store = store
    self.dest_root = dest_root
    self.emit = emit
    self.run_rar = run_rar or self._subprocess_rar

  @staticmethod
  def _subprocess_rar(args: list[str], timeout: float) -> tuple[int, str]:
    proc = subprocess.run([UNRAR_EXE, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, timeout=timeout)
    return proc.returncode, proc.stdout or proc.stderr or ""

  # ---- 计划 ----

  def plan(self) -> dict:
    """当前 pass 的分类。todo 里带 depth/parent_path/topic_id（执行时落库用）：
    顶层 = 父目录是 <root>/<纯数字 topic> 且 EroLink downloaded 行引用着；
    嵌套 = 落在某个 done 行的解压目录里（父 = 最深匹配），父未 done 先挂起
    （deferred，父成功后下轮自然接上）。"""
    archives = scan_archives(self.dest_root)
    rows = {r.archive_path: r
            for r in self.store.db.QueryRecords(EroExtract)}
    dl_paths = {r.dl_path.replace("\\", "/").lower()
                for r in self.store.db.QueryRecords(
                    EroLink, where="dl_status = ?", params=("downloaded",))
                if r.dl_path}
    prefixes = []   # done 行的解压输出前缀：(小写前缀, depth, archive_path)
    for rel, r in rows.items():
      if r.status != EX_DONE:
        continue
      d, b = posixpath.split(rel)
      prefixes.append((f"{posixpath.join(d, os.path.splitext(b)[0])}".lower() + "/",
                       r.depth, rel))
    result = {"todo": [], "done": [], "no_db": [], "deferred": []}
    for a in archives:
      rel, rl = a["rel"], a["rel"].lower()
      row = rows.get(rel)
      if row is not None and row.status == EX_DONE:
        result["done"].append(a)
        continue
      parent_dir = posixpath.dirname(rl)
      if parent_dir and "/" not in parent_dir and parent_dir.isdigit():
        if rl not in dl_paths:
          result["no_db"].append(a)
          continue
        a["depth"], a["parent_path"] = 1, ""
        a["topic_id"] = int(parent_dir)
      else:
        best = max((p for p in prefixes if rl.startswith(p[0])),
                   key=lambda p: len(p[0]), default=None)
        if best is None:
          result["deferred"].append(a)
          continue
        head = rl.split("/", 1)[0]
        a["depth"] = best[1] + 1
        a["parent_path"] = best[2]
        a["topic_id"] = int(head) if head.isdigit() else 0
      result["todo"].append(a)
    return result

  # ---- 执行 ----

  def _extract_one(self, a: dict) -> tuple[list[dict], int]:
    ext = os.path.splitext(a["abs"])[1].lower()
    if ext == ".zip":
      return extract_zip_file(a["abs"], self.dest_root)
    if ext == ".rar":
      return extract_rar_file(a["abs"], self.dest_root, self.run_rar)
    raise ExtractError("7z 无工具，人工处理")

  def run(self, topic_ids: set[int] = None) -> dict:
    """跑到不动点。pass N 解出的嵌套档案 pass N+1 接手；上限
    EXTRACT_DEPTH_MAX+1 个 pass——多出的那个 pass 专门把超深候选分类成
    failed（深度上限的包体在第 4 层才被发现，range(3) 走不到分类那步）。
    单次 run 内失败的包不跨 pass 重试（failed 行留给下次 run 续传）。
    totals: passes/extracted/failed/files/bytes/done_skip/no_db/deferred。"""
    totals = {"passes": 0, "extracted": 0, "failed": 0, "files": 0,
              "bytes": 0, "done_skip": 0, "no_db": 0, "deferred": 0}
    failed_this_run: set[str] = set()
    for _ in range(EXTRACT_DEPTH_MAX + 1):
      plan = self.plan()
      totals["done_skip"] = len(plan["done"])
      totals["no_db"] = len(plan["no_db"])
      totals["deferred"] = len(plan["deferred"])
      todo = [a for a in plan["todo"] if a["rel"] not in failed_this_run]
      if topic_ids:
        todo = [a for a in todo if a.get("topic_id") in topic_ids]
      if not todo:
        break
      totals["passes"] += 1
      for a in todo:
        if a["depth"] > EXTRACT_DEPTH_MAX:
          self._record(a, EX_FAILED, note="嵌套深度超上限，人工处理")
          failed_this_run.add(a["rel"])
          totals["failed"] += 1
          self.emit(f"  [深度超限] {a['rel']}")
          continue
        try:
          files, wrote = self._extract_one(a)
        except Exception as e:
          self._record(a, EX_FAILED, note=f"{type(e).__name__}: {e}")
          failed_this_run.add(a["rel"])
          totals["failed"] += 1
          self.emit(f"  [失败] {a['rel']}  {type(e).__name__}: {e}")
          continue
        self._record(a, EX_DONE, files=files)
        totals["extracted"] += 1
        totals["files"] += len(files)
        totals["bytes"] += wrote
        self.emit(f"  [解出] {a['rel']}  {len(files)} 文件"
                  f"  新写 {wrote / 1024 / 1024:.1f}MB")
    return totals

  def _record(self, a: dict, status: str, files: list = None, note: str = ""):
    self.store.mark_extract(a["rel"], status, topic_id=a.get("topic_id", 0),
                            depth=a.get("depth", 1),
                            parent_path=a.get("parent_path", ""),
                            files=files, note=note)
