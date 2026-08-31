
"""pairing 阶段核心：funscript ↔ 媒体分层匹配（配对决策表的生产版，
从 playground 草案 v3 实测转正）。纯逻辑零 IO 假设——时长探针注入。

分层（先到先得；层内多候选先 ffprobe 时长 ±2s 挑唯一，挑不出/并列归
ambiguous 交人工）：
  exact        stem 逐字符相等（normcase）
  axis+exact   剥多轴后缀（.pitch/.roll/...）后 exact
  fuzzy        NFKC+casefold+去非字母数字相等（视频 stem 先剥 _1080p 质量后缀）
  tagstrip     再剥一层尾随 (...) / [...] 标签后 fuzzy（作者署名/AV1 尾巴）
  contain      规范化后互含（min 6 字符；"[Chussy]"署名 / Hard-Soft 前缀形态）
  dur          名字层全空 -> 时长 ±2s 全树唯一命中（rule34 slug 名的主战场）
  provenance   救援层：名字/时长层全空或歧义时，发帖出处共位裁决——
               normalize 侧从 links_json 构造 {脚本rel: 媒体rel} 注入
               （同楼层 section='Script' 模板区脚本 + 恰一个媒体共现）。
               只救卡死的、不推翻名字层已配上的（幂等重跑零翻转）；
               时长降级为验证（脚本末动作早于片尾是常态），仅单向闸门：
               脚本比媒体长 >DUR_WEAK = 媒体疑似剪辑/预告，不出手
  single-video 帖内唯一媒体兜底（带时长闸门：脚本末动作与媒体差 >DUR_WEAK
               不硬配——分集帖脚本对不上唯一视频）

实测教训（草案三版迭代出的规则，勿随手删）：
  - 内容身份去重：脚本与媒体都按 (basename, size) 归并——root/解压包/嵌套包
    里的同名同体积副本就是镜像；同名不同体积是画质档（时长分不开，脚本
    时长已知挑 |Δ| 最小那档，否则默认大件）。
  - 音频次级目标：DLsite 音声包（wav+srt 无视频）——视频层全空后对音频
    跑同样分层，method 带 audio: 前缀。
时长另作验证器：名字层配上的对子标 dur✓（±2s）/ Δ（±10s 观察窗）/
dur✗（更大，保留配对但降置信）。
"""

import os
import re
import unicodedata
from collections import defaultdict
from typing import Callable

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".wmv", ".avi", ".mov", ".flv", ".ts",
              ".m4v", ".mpg", ".mpeg"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus"}
SCRIPT_EXTS = {".funscript", ".lua"}
AXIS_SUFFIXES = {"pitch", "roll", "twist", "sway", "surge", "yaw", "lurch"}
QUALITY_RE = re.compile(r"[ _\-.]*(2160p|1440p|1080p|720p|480p|360p|4k|60fps|30fps)$", re.I)
TAG_RE = re.compile(r"\s*[\(\[][^\(\)\[\]]*[\)\]]\s*$")

DUR_TIGHT = 2.0     # 强验证/提案窗（草案实测真对子窗）
DUR_WEAK = 10.0     # 记 Δ 不判死的观察窗；single 兜底闸门 / provenance 单向闸门用它
CONTAIN_MIN = 6

PAIRED, AMBIGUOUS, UNMATCHED = "paired", "ambiguous", "unmatched"


def normalize_stem(s: str) -> str:
  s = unicodedata.normalize("NFKC", s).casefold()
  return "".join(ch for ch in s if ch.isalnum())


def strip_axis_suffix(stem: str) -> tuple[str, str | None]:
  """'name.pitch' -> ('name', 'pitch')；无后缀 -> (stem, None)"""
  i = stem.rfind(".")
  if i > 0 and stem[i + 1:].lower() in AXIS_SUFFIXES:
    return stem[:i], stem[i + 1:].lower()
  return stem, None


def strip_quality_suffix(stem: str) -> str:
  """'hmv-dead_1080p' -> 'hmv-dead'（rule34 站点 slug 的质量尾巴）"""
  prev = None
  while prev != stem:
    prev, stem = stem, QUALITY_RE.sub("", stem)
  return stem


def strip_trailing_tag(stem: str) -> str:
  """剥一层尾随 (...) / [...]：'X (Less Vibrations)' -> 'X'"""
  return TAG_RE.sub("", stem)


def classify_media(files: list[str]) -> tuple[list[str], list[str], list[str]]:
  """[rel 路径] -> (视频, 音频, 脚本) 三列表，按扩展名分家"""
  vid, aud, scr = [], [], []
  for rel in files:
    ext = os.path.splitext(rel)[1].lower()
    if ext in VIDEO_EXTS:
      vid.append(rel)
    elif ext in AUDIO_EXTS:
      aud.append(rel)
    elif ext in SCRIPT_EXTS:
      scr.append(rel)
  return vid, aud, scr


def logical_scripts(files: list[str], size_of: Callable[[str], int]):
  """脚本按 (normcase basename, size) 内容身份归并：
  [{stem, size, paths}]——root/包内/嵌套包的同名同体积副本是镜像。"""
  groups: dict[tuple, dict] = {}
  for rel in files:
    base = os.path.basename(rel)
    size = size_of(rel)
    key = (os.path.normcase(base), size)
    g = groups.setdefault(key, {"stem": os.path.splitext(base)[0],
                                "size": size, "paths": []})
    g["paths"].append(rel)
  return [groups[k] for k in sorted(groups)]


def build_media_pool(entries: list[str], size_of: Callable[[str], int],
                     external: set[str] = frozenset()) -> dict:
  """媒体按 (normcase basename, size) 归并成候选池：
  {cid: {raw, n_raw, n_stripped, n_tag, rel, size, paths, external}}。
  rel 取字典序最小路径当代表（探时长/转码用），paths 全量记镜像。"""
  pool: dict[str, dict] = {}
  for rel in sorted(entries):
    base = os.path.basename(rel)
    stem = os.path.splitext(base)[0]
    size = size_of(rel)
    cid = f"{os.path.normcase(base)}|{size}"
    if cid not in pool:
      stripped = strip_quality_suffix(stem)
      pool[cid] = {"raw": stem, "n_raw": normalize_stem(stem),
                   "n_stripped": normalize_stem(stripped),
                   "n_tag": normalize_stem(strip_trailing_tag(stripped)),
                   "rel": rel, "size": size, "paths": [],
                   "external": rel in external}
    pool[cid]["paths"].append(rel)
  return pool


def _name_layers(stem: str, pool: dict) -> list[tuple[str, list[str]]]:
  """脚本 stem -> [(method, [cid])] 按层序（层内候选不分先后）"""
  base, axis = strip_axis_suffix(stem)
  n_raw, n_base = normalize_stem(stem), normalize_stem(base)
  n_stag = normalize_stem(strip_trailing_tag(base))
  by_layer: dict[str, list[str]] = defaultdict(list)
  for cid, c in pool.items():
    if os.path.normcase(stem) == os.path.normcase(c["raw"]):
      by_layer["exact" if not axis else "axis+exact"].append(cid)
      continue
    if axis and os.path.normcase(base) == os.path.normcase(c["raw"]):
      by_layer["axis+exact"].append(cid)
      continue
    if n_raw in (c["n_raw"], c["n_stripped"]) or \
       (axis and n_base in (c["n_raw"], c["n_stripped"])):
      by_layer["fuzzy" if not axis else "axis+fuzzy"].append(cid)
      continue
    if n_stag and n_stag == c["n_tag"]:
      by_layer["tagstrip" if not axis else "axis+tagstrip"].append(cid)
      continue
    a, b = n_base, c["n_stripped"]
    if len(a) >= CONTAIN_MIN and len(b) >= CONTAIN_MIN and (a in b or b in a):
      by_layer["contain"].append(cid)
  order = ["exact", "axis+exact", "fuzzy", "axis+fuzzy",
           "tagstrip", "axis+tagstrip", "contain"]
  return [(m, by_layer[m]) for m in order if by_layer.get(m)]


class TopicMatcher:
  """单帖匹配器。media_duration/script_duration 注入（真跑是 ffprobe /
  funscript JSON 解析，测试给假实现）。用法见 match()。"""

  def __init__(self, media_duration: Callable[[str], float | None],
               script_duration: Callable[[str], float | None]):
    self.media_duration = media_duration
    self.script_duration = script_duration

  def _dur(self, pool: dict, cid: str) -> float | None:
    return self.media_duration(pool[cid]["rel"])

  def _resolve(self, stem: str, sd: float | None, pool: dict,
               prefix: str = "") -> tuple[str | None, str, str]:
    """名字层 -> 候选裁决。返回 (cid, method, note)；cid None + method
    'ambiguous' 表示多候选挑不出；双 None 表示本池无命中。"""
    layers = _name_layers(stem, pool)
    for m, cands in layers:
      if len(cands) == 1:
        return cands[0], prefix + m, ""
      # 同名不同体积 = 画质档：时长分不开（内容同时长），脚本时长已知挑
      # |Δ| 最小那档（脚本配它写的那个剪辑），否则默认大件
      name = pool[cands[0]]["raw"].casefold()
      if len(cands) > 1 and all(pool[c]["raw"].casefold() == name for c in cands):
        order = sorted(cands, key=lambda c: -pool[c]["size"])
        pick, note = order[0], f"画质档{len(cands)}选1默认大件"
        if sd is not None:
          deltas = [((abs(d - sd) if (d := self._dur(pool, c)) is not None
                      else None), c) for c in order]
          known = [x for x in deltas if x[0] is not None]
          if known:
            best = min(known, key=lambda x: x[0])
            if best[0] <= DUR_WEAK:
              pick, note = best[1], f"画质档{len(cands)}选1Δ最小"
        return pick, prefix + m + "+画质档", note
      if sd is not None:
        hit = [c for c in cands
               if (d := self._dur(pool, c)) is not None and abs(d - sd) <= DUR_TIGHT]
        if len(hit) == 1:
          return hit[0], prefix + m + "+dur挑", ""
      return None, AMBIGUOUS, prefix + m
    # 名字层全空 -> 时长全树探（唯一命中才收，并列归 ambiguous）
    if sd is not None and pool:
      cand = [c for c in pool
              if (d := self._dur(pool, c)) is not None and abs(d - sd) <= DUR_TIGHT]
      if len(cand) == 1:
        return cand[0], prefix + "dur", ""
      if len(cand) > 1:
        return None, AMBIGUOUS, prefix + "dur探"
    return None, "", ""

  def match(self, vid_entries: list[str], aud_entries: list[str],
            script_entries: list[str], size_of: Callable[[str], int],
            external: set[str] = frozenset(),
            provenance: dict[str, str] | None = None) -> dict:
    """跑一个帖。provenance = {脚本 rel: 媒体 rel}（发帖出处共位信号，
    normalize 侧构造，见模块 docstring 的 provenance 层）。
    返回：
    rows: 每个逻辑脚本一行 {stem, size, paths, status, method, target_cid,
          target_pool, note, dur_mark}（target_pool 是 "video"|"audio"）
    pools: {"video": pool, "audio": pool}（拿 target 详情用）
    ambiguous / unmatched: [(stem, 说明)] / [(stem, 原因)]
    """
    vid_pool = build_media_pool(vid_entries, size_of, external)
    aud_pool = build_media_pool(aud_entries, size_of, external)
    scripts = logical_scripts(script_entries, size_of)
    rows, ambiguous, unmatched = [], [], []

    def single_fallback(sd, pool, pool_name):
      """帖内唯一媒体兜底，带时长闸门（分集帖 dur 差太远不硬配）"""
      if len(pool) != 1:
        return None, ""
      cid = next(iter(pool))
      if sd is None:
        return cid, ""
      d = self._dur(pool, cid)
      if d is None or abs(d - sd) <= DUR_WEAK:
        return cid, ""
      return None, (f"唯一{pool_name}时长对不上"
                    f"(脚本{sd:.0f}s vs {d:.0f}s,分集/剪辑?)")

    def finish(s, status, method, cid=None, pool=None, pool_name=None,
               note="", dur_mark=""):
      rows.append({"stem": s["stem"], "size": s["size"], "paths": s["paths"],
                   "status": status, "method": method, "target_cid": cid,
                   "target_pool": pool_name, "note": note, "dur_mark": dur_mark})

    for s in scripts:
      # 脚本时长取镜像代表（内容相同取哪个都一样）
      sd = None
      for p in s["paths"]:
        sd = self.script_duration(p)
        if sd is not None:
          break

      cid, method, note = self._resolve(s["stem"], sd, vid_pool)
      pool, pool_name = vid_pool, "video"
      if not cid and method != AMBIGUOUS:
        cid, method, note = self._resolve(s["stem"], sd, aud_pool, prefix="audio:")
        pool, pool_name = aud_pool, "audio"
      # 出处救援：名字/时长层全空或歧义才出手（已配上的不动，幂等重跑
      # 零翻转）。作者共位意图强于单纯唯一性，排在 single 兜底之前。
      if not cid and provenance:
        hint = next((provenance[p] for p in s["paths"] if p in provenance), None)
        if hint:
          for pool_x, name_x in ((vid_pool, "video"), (aud_pool, "audio")):
            hcid = next((c for c, ent in pool_x.items()
                         if hint in ent["paths"]), None)
            if hcid is None:
              continue
            d = self._dur(pool_x, hcid)
            # 单向闸门：脚本显著长于媒体 = 媒体疑似剪辑/预告，共位也不硬配；
            # 反向（脚本早完）是 funscript 常态，时长只作验证不拦
            if sd is None or d is None or sd - d <= DUR_WEAK:
              cid, method, note = hcid, "provenance", ""
              pool, pool_name = pool_x, name_x
            break
      single_note = ""
      if not cid and method != AMBIGUOUS:
        cid, single_note = single_fallback(sd, vid_pool, "视频")
        if cid:
          method, pool, pool_name = "single-video", vid_pool, "video"
      if not cid and method != AMBIGUOUS and not single_note:
        cid, single_note = single_fallback(sd, aud_pool, "音频")
        if cid:
          method, pool, pool_name = "single-audio", aud_pool, "audio"

      if method == AMBIGUOUS:
        finish(s, AMBIGUOUS, note)
        ambiguous.append((s["stem"], note))
        continue
      if not cid:
        finish(s, UNMATCHED, "", note=single_note)
        unmatched.append((s["stem"], single_note))
        continue

      dur_mark = note
      if sd is not None:
        d = self._dur(pool, cid)
        if d is not None:
          delta = d - sd
          dur_mark += " " if dur_mark else ""
          dur_mark += ("dur✓" if abs(delta) <= DUR_TIGHT else
                       (f"Δ{delta:+.1f}s" if abs(delta) <= DUR_WEAK
                        else f"dur✗{delta:+.0f}s"))
      finish(s, PAIRED, method, cid=cid, pool=pool, pool_name=pool_name,
             dur_mark=dur_mark)
    return {"rows": rows, "pools": {"video": vid_pool, "audio": aud_pool},
            "ambiguous": ambiguous, "unmatched": unmatched}
