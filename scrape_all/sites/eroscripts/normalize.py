
"""normalize 阶段核心：es_scrape（原始库，只读不动）→ es_norm（归一化库）。

配对（pairing.TopicMatcher）成功的组落位规则：
  - 媒体 + 主脚本同 stem 平铺在 <topic>/<stem>.<ext>
  - 多轴脚本 <stem>.<axis>.funscript（播放器联动约定）
  - 强度/设备变体脚本 <topic>/variants/ 原名
  - 主脚本 = 平凡原始（无轴后缀无尾随标签）唯一者；缺平凡原始时按
    PRIORITY_PATTERNS 优先级表（子串匹配，先到先得）把第一提为主脚本，
    表无命中整组挂起（pending，人工裁决后重跑幂等补进）
  - 组内多个平凡原始候选同样挂起（人工裁决）
- 视频：任一边 >1500 -> ffmpeg x264 crf20 medium 对半除重编码出 mp4
  （2 的整数次幂除到 (750,1500]，音频直通，直通失败回退 aac；转码后
  ffprobe 时长核验）；两边都 <=1500 文件直拷。
  音频媒体（音声包配对）无缩放概念，直拷。
- 幂等：EroNorm（target_path 主键）done 且盘上核验过跳过；failed 重跑重试。
  源库不动、决策确定性 → 增量运行自动接新配对/新帖。

CLI 在 scripts/normalize_library.py；本模块依赖注入 store / run_ffmpeg /
probe，全部逻辑可离线单测。
"""

import json
import math
import os
import shutil
import subprocess
from typing import Callable

from scrape_all.sites.eroscripts import pairing
from scrape_all.sites.eroscripts.history import to_iso
from scrape_all.sites.eroscripts.pairing import (
    PAIRED, VIDEO_EXTS, AUDIO_EXTS, SCRIPT_EXTS,
    normalize_stem, strip_axis_suffix, strip_trailing_tag,
)
from scrape_all.storage.models import EroLink, EroNorm, EroTopicItem

NORM_MAX_LONG_EDGE = 1500    # 归一化阈值（atplayer 同款）：任一边超过即
                              # 对半除——1920x1080 -> 960x540（÷2），
                              # 3840x2160 -> 960x540（÷4），2560x1440 ->
                              # 1280x720（÷2），2000x1500 -> 1000x750（÷2）；
                              # 两边都 <= 1500 原样 copy。
VARIANTS_DIR = "variants"
FFMPEG_EXE = r"E:\Program Files\ffmpeg\bin\ffmpeg.EXE"
FFPROBE_EXE = r"E:\Program Files\ffmpeg\bin\ffprobe.EXE"
FFMPEG_TIMEOUT_S = 3600.0
VIDEO_CRF = "20"
VIDEO_PRESET = "medium"

# 变体优先级表：子串列表（对脚本 stem casefold 匹配，先到先得）。
# 缺平凡原始/多平凡原始的组靠它定主脚本；同一子串命中多个候选时取
# 最短 stem（修饰最少的最接近平凡原始，如 "Sherry…" 平凡版是
# "(Stronger End) Sherry…" 的子串，靠长度决胜选出前者）；无命中的组
# 挂起等人工。由用户裁决后维护。
PRIORITY_PATTERNS: list[str] = [
    # 307720 多轴套餐为主（pitch/roll/twist 保住轴位），single-axis 进变体
    "multi-axis",
    # 307726 Shupogaki 双角色取 Nozomi（385 动作 vs Hikari 263，轨道更密）
    "(nozomi)",
    # 312236 同内容双命名（MD5 相同）：取帖子直传的无撇号版
    "ina nis",
    # 324307 8 连变体取 Hard 基线（无 Smooth/Vibro 修饰）
    "hard paizuri",
    # 328160 平凡版为主，(Stronger End) 进变体（长度决胜）
    "sherry birkin",
    # 329619 fap-hero 取 Hard（Soft 是降档替代）
    "hard fap-hero",
]

NORM_DONE, NORM_FAILED = "done", "failed"

KIND_VIDEO, KIND_AUDIO, KIND_SCRIPT = "video", "audio", "script"
KIND_AXIS, KIND_VARIANT = "axis-script", "variant-script"


def _now_iso() -> str:
  from datetime import datetime, timezone
  return to_iso(datetime.now(timezone.utc).replace(tzinfo=None))


# ---- ffprobe / ffmpeg ----

def ffprobe_json(path: str) -> dict | None:
  try:
    r = subprocess.run(
        [FFPROBE_EXE, "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout) if r.returncode == 0 else None
  except (OSError, ValueError, subprocess.SubprocessError):
    return None


def media_info(path: str) -> dict | None:
  """ffprobe 摘要：{duration, width, height, long_edge}。旋转元数据
  （90/270）下显示宽高互换——long_edge 取 max(宽,高)，旋转不改变最大值，
  缩放表达式按编码宽高取大边即可。非视频/失败返回 None。"""
  j = ffprobe_json(path)
  if not j:
    return None
  info = {"duration": None, "width": None, "height": None, "long_edge": None}
  try:
    info["duration"] = float(j["format"]["duration"])
  except (KeyError, ValueError, TypeError):
    pass
  for st in j.get("streams", []):
    if st.get("codec_type") == "video" and st.get("width") and st.get("height"):
      info["width"], info["height"] = st["width"], st["height"]
      info["long_edge"] = max(st["width"], st["height"])
      break
  return info


def funscript_duration(path: str) -> float | None:
  """末动作时刻 ms->s；lua 无固定格式返回 None"""
  try:
    acts = json.load(open(path, encoding="utf-8", errors="replace")).get("actions") or []
    return acts[-1]["at"] / 1000 if acts else None
  except (OSError, ValueError, KeyError, IndexError):
    return None


class DiskCachedProbe:
  """ffprobe 结果落盘缓存（key=path|size|mtime，产物变更自动失效）。
  dry-run 与 execute 两轮、多次增量重跑不再重复探 600+ 文件。"""

  def __init__(self, cache_path: str):
    self.cache_path = cache_path
    self.data: dict[str, dict | None] = {}
    if os.path.exists(cache_path):
      try:
        self.data = json.load(open(cache_path, encoding="utf-8"))
      except (OSError, ValueError):
        self.data = {}

  def __call__(self, path: str) -> dict | None:
    try:
      st = os.stat(path)
    except OSError:
      return media_info(path)
    key = f"{os.path.normcase(path)}|{st.st_size}|{int(st.st_mtime)}"
    if key not in self.data:
      self.data[key] = media_info(path)
    return self.data[key]

  def save(self):
    try:
      json.dump(self.data, open(self.cache_path, "w", encoding="utf-8"),
                ensure_ascii=False)
    except OSError:
      pass


def _subprocess_ffmpeg(args: list[str], timeout: float) -> tuple[int, str]:
  proc = subprocess.run([FFMPEG_EXE, *args], capture_output=True, text=True,
                        encoding="utf-8", errors="replace",
                        stdin=subprocess.DEVNULL, timeout=timeout)
  return proc.returncode, proc.stdout or proc.stderr or ""


# ---- 主脚本选择 ----

def classify_script_stem(stem: str) -> dict:
  base, axis = strip_axis_suffix(stem)
  return {"stem": stem, "base": base, "axis": axis,
          "tagged": strip_trailing_tag(base) != base}


def _priority_pick(cands: list[dict], priority: list[str]) -> dict | None:
  """优先级表裁决：按表序找第一个有候选命中的子串，命中的候选里取
  最短 stem（修饰最少的最接近平凡原始——平凡版常是变体版的子串，
  如 "Sherry…" vs "(Stronger End) Sherry…"，纯子串分不出，靠长度）。
  全无命中返回 None（调用方挂起）。"""
  for pat in priority:
    hits = [c for c in cands if pat.casefold() in c["stem"].casefold()]
    if hits:
      return min(hits, key=lambda c: (len(c["stem"]), c["stem"]))
  return None


def pick_primary(stems: list[str],
                 priority: list[str] | None = None) -> dict:
  """组内主脚本决策。返回 {primary, axis, variants, pending}：primary None
  且 pending 非空 = 整组挂起（不落位不落库，人工裁决后重跑）。

  - 组内只有一个非轴脚本 -> 它就是主（Iwara "[Source]"/"[Chussy]"署名
    这类尾巴不构成变体形态，单脚本组不该挂起）
  - 多个非轴脚本：恰有一个是其余全部的前缀（_hand / FAST / .raw /
    "基名[Source]"+".p/.s/.t" 缩写轴形态）-> 前缀者是主、其余算变体；
    平凡原始（无尾随标签）唯一 -> 它；多个平凡原始或全带尾标签（真·
    平级脚本对同一视频：Hard/Soft、Hikari/Nozomi、multi/single-axis）
    -> PRIORITY_PATTERNS 优先级表定主（子串匹配表序先到先得），
    无命中挂起
  """
  priority = PRIORITY_PATTERNS if priority is None else priority
  infos = [classify_script_stem(s) for s in stems]
  non_axis = [i for i in infos if i["axis"] is None]
  if not non_axis:
    return {"primary": None, "axis": [], "variants": [],
            "pending": "只有多轴脚本无主脚本"}
  if len(non_axis) == 1:
    primary = non_axis[0]
  else:
    # 前缀归一（优先）：恰有一个非轴 stem 是其余全部的前缀 -> 它是基名，
    # 其余是变体（_hand / FAST / .raw 形态，以及 "基名[Source]" + ".p/.s/.t"
    # 缩写轴形态——基名带 Iwara 尾标签不妨碍它是主）
    primary = next((c for c in non_axis
                    if all(i["stem"] == c["stem"]
                           or i["stem"].startswith(c["stem"])
                           for i in non_axis)), None)
    if primary is None:
      plains = [i for i in non_axis if not i["tagged"]]
      if len(plains) == 1:
        primary = plains[0]
      elif len(plains) > 1:
        # 多个平凡原始也是平级脚本之争（Hard/Soft、"Stronger End" 版），
        # 优先级表同样裁决；无命中才挂起
        primary = _priority_pick(plains, priority)
        if primary is None:
          return {"primary": None, "axis": [], "variants": [],
                  "pending": "多个平凡原始候选: "
                             + ", ".join(i["stem"] for i in plains)}
      else:
        primary = _priority_pick(non_axis, priority)
        if primary is None:
          return {"primary": None, "axis": [], "variants": [],
                  "pending": "缺平凡原始且优先级表无命中"}
  pb = normalize_stem(strip_trailing_tag(primary["base"]))
  axis = [i for i in infos
          if i["axis"] and normalize_stem(strip_trailing_tag(i["base"])) == pb]
  variants = [i for i in infos
              if i["stem"] != primary["stem"] and i not in axis]
  return {"primary": primary, "axis": axis, "variants": variants, "pending": ""}


# ---- 编排 ----

def group_by_target(result: dict) -> list[dict]:
  """pairing.match 结果 -> 按 (target_pool, target_cid) 分组
  [{pool_name, media, scripts:[row...]}]（media 是池条目）"""
  groups: dict[tuple, dict] = {}
  for r in result["rows"]:
    if r["status"] != PAIRED:
      continue
    key = (r["target_pool"], r["target_cid"])
    g = groups.setdefault(key, {"pool_name": r["target_pool"], "scripts": []})
    g["scripts"].append(r)
  out = []
  for (pool_name, cid), g in groups.items():
    g["media"] = result["pools"][pool_name][cid]
    g["pool_name"] = pool_name
    out.append(g)
  out.sort(key=lambda g: g["media"]["rel"])
  return out


def transcode_plan(info: dict | None) -> tuple[bool, str | None]:
  """(要否重编码, -vf 表达式)。任一边 > NORM_MAX_LONG_EDGE -> 按 2 的
  整数次幂对半除（atplayer normalize_media_in_folder 同款算法）：宽高
  各除以阈值取 log2，较大者 ceil 出需要的减半次数，factor = 2^次数，
  目标 = 原尺寸整除 factor 后各自取偶（x264 要求）。两边都不超 ->
  copy。输出长边落在 (阈值/2, 阈值]。探不到尺寸 = 无法裁决，交调用方
  挂起。"""
  if not info or not info.get("width") or not info.get("height"):
    return False, None
  w, h = info["width"], info["height"]
  max_div = max(math.log2(w / NORM_MAX_LONG_EDGE),
                math.log2(h / NORM_MAX_LONG_EDGE))
  factor = 2 ** math.ceil(max_div) if max_div > 0.0 else 0
  if factor <= 0:
    return False, None
  tw = round((w // factor) / 2) * 2
  th = round((h // factor) / 2) * 2
  return True, f"scale={tw}:{th}"


class LibraryNormalizer:
  """es_scrape -> es_norm。scan（全树 + EroLink 外帖入池）-> 每帖
  pairing.match -> pick_primary -> 落位（copy / transcode）-> EroNorm 落库。"""

  def __init__(self, store, src_root: str, dst_root: str,
               emit: Callable[[str], None] = print,
               run_ffmpeg: Callable[[list[str], float], tuple[int, str]] = None,
               probe: Callable[[str], dict | None] = None,
               priority: list[str] | None = None):
    self.store = store
    self.src_root = src_root
    self.dst_root = dst_root
    self.emit = emit
    self.run_ffmpeg = run_ffmpeg or _subprocess_ffmpeg
    self.probe = probe or media_info
    self.priority = priority
    self._info_cache: dict[str, dict | None] = {}

  # ---- 素材 ----

  def scan_topics(self) -> dict[str, dict[str, list[str]]]:
    """{tid: {vid, aud, scr}}（rel '/' 风格，含解压子目录全树）"""
    topics: dict[str, dict[str, list[str]]] = {}
    for dirpath, _dn, fns in os.walk(self.src_root):
      rel_dir = os.path.relpath(dirpath, self.src_root)
      if rel_dir == ".":
        continue
      tid = rel_dir.split(os.sep)[0]
      if not tid.isdigit():
        continue
      t = topics.setdefault(tid, {"vid": [], "aud": [], "scr": []})
      for fn in fns:
        ext = os.path.splitext(fn)[1].lower()
        rel = os.path.join(rel_dir, fn).replace(os.sep, "/")
        if ext in VIDEO_EXTS:
          t["vid"].append(rel)
        elif ext in AUDIO_EXTS:
          t["aud"].append(rel)
        elif ext in SCRIPT_EXTS:
          t["scr"].append(rel)
    return topics

  def external_rels(self, tid: str) -> set[str]:
    """帖自身 EroLink downloaded media/source 的 dl_path 指到的媒体
    （共享 URL 落他帖目录 / gofile 文件夹链接 dl_path 只记目录——目录型
    整目录walk入池）。返回 rel 集，本帖树内的不算（walk 已覆盖）。"""
    out: set[str] = set()
    topic = self.store.db.QueryOne(EroTopicItem, where="topic_id = ?",
                                   params=(int(tid),))
    if topic is None:
      return out
    try:
      urls = [l.get("url") for l in json.loads(topic.links_json or "[]")]
    except (ValueError, AttributeError, TypeError):
      return out
    for url in filter(None, urls):
      row = self.store.db.QueryOne(EroLink, where="url = ?", params=(url,))
      if (row is None or row.kind not in ("media", "source")
          or row.dl_status != "downloaded" or not row.dl_path):
        continue
      rel = row.dl_path.replace("\\", "/")
      if rel.split("/")[0] == tid:
        continue
      abspath = os.path.join(self.src_root, rel)
      if os.path.isdir(abspath):
        for dp, _dn2, fns in os.walk(abspath):
          for fn in fns:
            if os.path.splitext(fn)[1].lower() in (VIDEO_EXTS | AUDIO_EXTS):
              out.add(os.path.relpath(os.path.join(dp, fn),
                                      self.src_root).replace(os.sep, "/"))
      elif os.path.isfile(abspath) and \
          os.path.splitext(rel)[1].lower() in (VIDEO_EXTS | AUDIO_EXTS):
        out.add(rel)
    return out

  # ---- 路径 / 探针 ----

  def _abs(self, rel: str) -> str:
    return os.path.join(self.src_root, *rel.split("/"))

  def _size_of(self, rel: str) -> int:
    try:
      return os.path.getsize(self._abs(rel))
    except OSError:
      return 0

  def _probe_rel(self, rel: str) -> dict | None:
    if rel not in self._info_cache:
      self._info_cache[rel] = self.probe(self._abs(rel))
    return self._info_cache[rel]

  def _media_duration(self, rel: str) -> float | None:
    info = self._probe_rel(rel)
    return info.get("duration") if info else None

  def _script_duration(self, rel: str) -> float | None:
    return funscript_duration(self._abs(rel))

  # ---- 落位 ----

  def _norm_row(self, target_path: str) -> EroNorm | None:
    return self.store.db.QueryOne(EroNorm, where="target_path = ?",
                                  params=(target_path,))

  def _already_done(self, target_abs: str, source_size: int,
                    row: EroNorm | None) -> bool:
    """done 行 + 盘上核验：copy 体积精确对上；transcode 存在且非 0。"""
    if row is None or row.status != NORM_DONE:
      return False
    if not os.path.exists(target_abs):
      return False
    if row.action == "copy":
      return os.path.getsize(target_abs) == source_size
    return os.path.getsize(target_abs) > 0

  def _resolve_target(self, reserved: set[str], target_rel: str,
                      source_rel: str) -> str:
    """落位目标裁决：目标未被本次运行占用、库行要么没有要么 source 就是
    本源、盘上无来历不明文件 -> 原样（幂等重跑必须拿到同一路径才能对上
    done 行跳过）；被不同源占用 -> {stem}.{token}{ext} 第二把。"""

    def free(rel: str) -> bool:
      if rel in reserved:
        return False
      row = self._norm_row(rel)
      if row is not None and row.source_path != source_rel:
        return False
      if row is None and os.path.exists(
          os.path.join(self.dst_root, *rel.split("/"))):
        return False
      return True

    if free(target_rel):
      reserved.add(target_rel)
      return target_rel
    stem, ext = os.path.splitext(target_rel)
    token = _token(source_rel)
    alt = f"{stem}.{token}{ext}"
    n = 2
    while not free(alt):
      alt = f"{stem}.{token}.{n}{ext}"
      n += 1
    reserved.add(alt)
    return alt

  def _transcode(self, src_abs: str, out_abs: str, vf: str) -> str:
    """x264 crf20 medium + 音频直通（直通失败回退 aac）。成功返回 ""，
    失败返回原因（半成品已清）。"""
    base = ["-y", "-i", src_abs, "-vf", vf, "-c:v", "libx264",
            "-crf", VIDEO_CRF, "-preset", VIDEO_PRESET]
    tail = ["-movflags", "+faststart", out_abs]
    rc, _ = self.run_ffmpeg(base + ["-c:a", "copy"] + tail, FFMPEG_TIMEOUT_S)
    if rc != 0:
      rc, _ = self.run_ffmpeg(base + ["-c:a", "aac", "-b:a", "192k"] + tail,
                              FFMPEG_TIMEOUT_S)
    if rc != 0:
      if os.path.exists(out_abs):
        os.remove(out_abs)
      return f"ffmpeg 退出码 {rc}"
    out_info = self.probe(out_abs)
    if not out_info or not out_info.get("duration"):
      if os.path.exists(out_abs):
        os.remove(out_abs)
      return "转码产物 ffprobe 核验失败"
    return ""

  def _emit_file(self, tid: int, kind: str, source_rel: str, target_rel: str,
                 action: str, reserved: set[str], execute: bool) -> str:
    """单文件落位。返回 'done'|'skip'|'failed:<原因>'（dry-run 返回 'plan'）。
    目标先 _resolve_target：幂等重跑拿回原路径对 done 行，异源撞名让位。"""
    target_rel = self._resolve_target(reserved, target_rel, source_rel)
    target_abs = os.path.join(self.dst_root, *target_rel.split("/"))
    source_abs = self._abs(source_rel)
    source_size = self._size_of(source_rel)
    row = self._norm_row(target_rel)
    if self._already_done(target_abs, source_size, row):
      return "skip"
    if not execute:
      return "plan"
    os.makedirs(os.path.dirname(target_abs), exist_ok=True)
    try:
      if action == "copy":
        if not os.path.isfile(source_abs):
          raise FileNotFoundError(source_rel)
        shutil.copy2(source_abs, target_abs)
        if os.path.getsize(target_abs) != source_size:
          raise IOError("复制体积不符")
      else:   # transcode
        err = self._transcode(source_abs, target_abs, action)
        if err:
          raise IOError(err)
    except (OSError, IOError) as e:
      self.store.mark_norm(target_rel, tid, source_path=source_rel, kind=kind,
                           action=action, status=NORM_FAILED, note=str(e))
      return f"failed:{e}"
    self.store.mark_norm(target_rel, tid, source_path=source_rel, kind=kind,
                         action=action, status=NORM_DONE)
    return "done"

  # ---- 主流程 ----

  def _plan_groups(self, tid: str, t: dict) -> tuple[list[dict], list[dict], dict]:
    """单帖：match -> groups（补 pick_primary 决策 + 媒体 action）。"""
    external = self.external_rels(tid)
    matcher = pairing.TopicMatcher(self._media_duration, self._script_duration)
    result = matcher.match(
        t["vid"] + sorted(r for r in external
                          if os.path.splitext(r)[1].lower() in VIDEO_EXTS),
        t["aud"] + sorted(r for r in external
                          if os.path.splitext(r)[1].lower() in AUDIO_EXTS),
        t["scr"], self._size_of,
        external=external)
    groups = group_by_target(result)
    planned, pending = [], []
    for g in groups:
      media_rel = g["media"]["rel"]
      info = self._probe_rel(media_rel) if g["pool_name"] == "video" else None
      if g["pool_name"] == "video" and not info:
        pending.append({"tid": tid, "media": media_rel,
                        "stems": [r["stem"] for r in g["scripts"]],
                        "reason": "视频 ffprobe 探不到尺寸/时长"})
        continue
      sel = pick_primary([r["stem"] for r in g["scripts"]], self.priority)
      if sel["pending"]:
        pending.append({"tid": tid, "media": media_rel,
                        "stems": [r["stem"] for r in g["scripts"]],
                        "reason": sel["pending"]})
        continue
      need, vf = transcode_plan(info)
      planned.append({"tid": tid, "sel": sel, "media": g["media"],
                      "pool_name": g["pool_name"], "transcode": need,
                      "vf": vf, "scripts": g["scripts"]})
    return planned, pending, result

  def run(self, topic_ids: set[int] = None, execute: bool = True) -> dict:
    """全量/按帖跑。dry-run（execute=False）只出计划不动盘不动库。"""
    totals = {"topics": 0, "groups": 0, "files": 0, "copied": 0,
              "transcoded": 0, "skip": 0, "failed": 0, "pending_groups": 0,
              "ambiguous": 0, "unmatched": 0}
    topics = self.scan_topics()
    for tid in sorted(topics, key=int):
      if topic_ids and int(tid) not in topic_ids:
        continue
      if not topics[tid]["scr"]:
        continue
      totals["topics"] += 1
      planned, pending, result = self._plan_groups(tid, topics[tid])
      totals["ambiguous"] += len(result["ambiguous"])
      totals["unmatched"] += len(result["unmatched"])
      totals["pending_groups"] += len(pending)
      for p in pending:
        self.emit(f"  [挂起] topic {p['tid']}  {p['media']}")
        self.emit(f"        {p['reason']}  候选: {p['stems']}")
      reserved: set[str] = set()
      for g in planned:
        totals["groups"] += 1
        stem = g["sel"]["primary"]["stem"]
        ext = os.path.splitext(g["media"]["rel"])[1]
        is_video = g["pool_name"] == "video"
        if is_video and g["transcode"]:
          action, media_ext = g["vf"], ".mp4"
        else:
          action, media_ext = "copy", ext
        jobs = [(KIND_VIDEO if is_video else KIND_AUDIO, g["media"]["rel"],
                 f"{tid}/{stem}{media_ext}", action)]
        primary_row = next(r for r in g["scripts"]
                           if r["stem"] == g["sel"]["primary"]["stem"])
        jobs.append((KIND_SCRIPT, primary_row["paths"][0],
                     f"{tid}/{stem}{_script_ext(primary_row['paths'][0])}",
                     "copy"))
        for a in g["sel"]["axis"]:
          src = next(r for r in g["scripts"] if r["stem"] == a["stem"])["paths"][0]
          jobs.append((KIND_AXIS, src,
                       f"{tid}/{stem}.{a['axis']}{_script_ext(src)}", "copy"))
        for v in g["sel"]["variants"]:
          src = next(r for r in g["scripts"] if r["stem"] == v["stem"])["paths"][0]
          jobs.append((KIND_VARIANT, src,
                       f"{tid}/{VARIANTS_DIR}/{v['stem']}{_script_ext(src)}",
                       "copy"))
        desc = (f"[转码 {g['vf']}]" if action != "copy" else "[直拷]")
        if not execute:
          self.emit(f"  topic {tid}  {desc}  {os.path.basename(g['media']['rel'])}"
                    f"  -> {stem}{media_ext}"
                    f"  脚本 {len(g['scripts'])}(轴{len(g['sel']['axis'])}"
                    f" 变体{len(g['sel']['variants'])})")
        for kind, src, target, act in jobs:
          totals["files"] += 1
          st = self._emit_file(int(tid), kind, src, target, act,
                               reserved, execute)
          if st == "done":
            totals["copied" if act == "copy" else "transcoded"] += 1
          elif st == "skip":
            totals["skip"] += 1
          elif st.startswith("failed"):
            totals["failed"] += 1
            self.emit(f"  [失败] {target}  {st[8:]}")
    return totals


def _script_ext(rel: str) -> str:
  return os.path.splitext(rel)[1].lower() or ".funscript"


def _token(rel: str) -> str:
  from scrape_all.downloader.fsutil import url_token
  return url_token(rel)
