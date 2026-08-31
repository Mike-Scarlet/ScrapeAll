import json
import os

import pytest

from scrape_all.sites.eroscripts.pairing import (
    AMBIGUOUS, PAIRED, UNMATCHED, TopicMatcher, build_media_pool,
    logical_scripts, normalize_stem, strip_axis_suffix,
    strip_quality_suffix, strip_trailing_tag,
)

TOPIC = 307001


def make_tree(tmp_path, tid, files: dict[str, bytes]):
  root = tmp_path / "scrape"
  for rel, data in files.items():
    p = root / str(tid) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
  return root


def fs(root):
  return lambda rel: os.path.getsize(os.path.join(str(root), *rel.split("/")))


def rels(root, tid):
  """该帖全树 rel 列表"""
  base = os.path.join(str(root), str(tid))
  out = []
  for dp, _dn, fns in os.walk(base):
    for fn in fns:
      out.append(os.path.relpath(os.path.join(dp, fn),
                                 str(root)).replace(os.sep, "/"))
  return out


def fs_script(content_actions):
  return json.dumps({"actions": [{"at": a, "pos": 0} for a in content_actions],
                     "version": "1.0"}).encode()


@pytest.fixture
def env(tmp_path):
  """媒体/脚本时长全由 dict 提供，测试完全不碰 ffprobe"""
  env.media_dur: dict[str, float] = {}
  env.script_dur: dict[str, float] = {}
  env.root = None
  env.matcher = TopicMatcher(
      lambda rel: env.media_dur.get(rel),
      lambda rel: env.script_dur.get(rel))
  env.tmp = tmp_path
  return env


def run_topic(env, tid, files, provenance=None):
  env.root = make_tree(env.tmp, tid, files)
  all_rels = rels(env.root, tid)
  vid = [r for r in all_rels if os.path.splitext(r)[1].lower() == ".mp4"]
  aud = [r for r in all_rels if os.path.splitext(r)[1].lower() == ".wav"]
  scr = [r for r in all_rels if r.endswith(".funscript")]
  return env.matcher.match(vid, aud, scr, fs(env.root), provenance=provenance)


def by_stem(result, stem):
  return next(r for r in result["rows"] if r["stem"] == stem)


# ---- 纯函数 ----

def test_stem_helpers():
  assert normalize_stem("ＨＭＶ ｄｅａｄ！") == "hmvdead"     # NFKC 全角折半角
  assert strip_axis_suffix("X.pitch") == ("X", "pitch")
  assert strip_axis_suffix("X") == ("X", None)
  assert strip_quality_suffix("hmv-dead_1080p_60fps") == "hmv-dead"
  assert strip_quality_suffix("plain") == "plain"
  assert strip_trailing_tag("X (Less Vibrations)") == "X"
  assert strip_trailing_tag("X [Chussy]") == "X"
  assert strip_trailing_tag("X") == "X"


def test_logical_scripts_mirror_merge(tmp_path):
  root = make_tree(tmp_path, TOPIC, {
      "X.funscript": fs_script([0, 1000]),
      "pkg/X.funscript": fs_script([0, 1000]),        # 同名同体积 = 镜像
      "pkg/X2.funscript": fs_script([0, 2000]),       # 同名不同体积 = 修订版
  })
  scr = [r for r in rels(root, TOPIC) if r.endswith(".funscript")]
  logi = logical_scripts(scr, fs(root))
  assert len(logi) == 2
  x = next(g for g in logi if g["stem"] == "X")
  assert len(x["paths"]) == 2


def test_build_media_pool_mirror_and_tier(tmp_path):
  root = make_tree(tmp_path, TOPIC, {
      "V.mp4": b"a" * 100,
      "pkg/V.mp4": b"a" * 100,          # 镜像
      "src/V.mp4": b"a" * 500,          # 画质档（同名不同体积）
  })
  vid = [r for r in rels(root, TOPIC) if r.endswith(".mp4")]
  pool = build_media_pool(vid, fs(root))
  assert len(pool) == 2
  sizes = sorted(c["size"] for c in pool.values())
  assert sizes == [100, 500]
  mirror = next(c for c in pool.values() if c["size"] == 100)
  assert len(mirror["paths"]) == 2


# ---- 匹配分层 ----

def test_exact_and_axis_pair(env):
  r = run_topic(env, TOPIC, {
      "X.mp4": b"v",
      "X.funscript": fs_script([0, 999]),
      "X.pitch.funscript": fs_script([0, 999]),
  })
  a, b = by_stem(r, "X"), by_stem(r, "X.pitch")
  assert a["status"] == PAIRED and a["method"] == "exact"
  assert b["status"] == PAIRED and b["method"] == "axis+exact"
  assert a["target_cid"] == b["target_cid"]


def test_fuzzy_quality_suffix(env):
  r = run_topic(env, TOPIC, {
      "hmv-dead_1080p.mp4": b"v",
      "Hmv Dead!.funscript": fs_script([0, 999]),
  })
  assert by_stem(r, "Hmv Dead!")["method"] == "fuzzy"


def test_tagstrip_author_or_variant_tag(env):
  r = run_topic(env, TOPIC, {
      "hmv-dead_1080p.mp4": b"v",
      "HMV - DEAD [Chussy].funscript": fs_script([0, 999]),
  })
  assert by_stem(r, "HMV - DEAD [Chussy]")["method"] == "tagstrip"


def test_contain_prefix_form(env):
  # tagstrip 后仍不等（Hard 前缀残留）-> 规范化互含兜住
  r = run_topic(env, TOPIC, {
      "paizuri-paradise_1080p.mp4": b"v",
      "Hard Paizuri_Paradise.funscript": fs_script([0, 999]),
  })
  assert by_stem(r, "Hard Paizuri_Paradise")["method"] == "contain"


def test_duration_proposal_when_names_dead(env):
  env.media_dur = {f"{TOPIC}/some-random-slug_1080p.mp4": 123.4}
  env.script_dur = {f"{TOPIC}/罗马字名.funscript": 123.9}
  r = run_topic(env, TOPIC, {
      "some-random-slug_1080p.mp4": b"v",
      "罗马字名.funscript": fs_script([0, 123900]),
  })
  row = by_stem(r, "罗马字名")
  assert row["status"] == PAIRED and row["method"] == "dur"


def test_tier_picks_min_delta(env):
  # 同名双档：小档 200s（脚本 200.5s），大档 210s -> 挑 Δ 最小的小档
  env.media_dur = {f"{TOPIC}/V.mp4": 200.0, f"{TOPIC}/src/V.mp4": 210.0}
  env.script_dur = {f"{TOPIC}/V.funscript": 200.5}
  r = run_topic(env, TOPIC, {
      "V.mp4": b"a" * 100,
      "src/V.mp4": b"a" * 5000,
      "V.funscript": fs_script([0, 200500]),
  })
  row = by_stem(r, "V")
  assert row["method"] == "exact+画质档"
  pool = r["pools"]["video"]
  assert pool[row["target_cid"]]["size"] == 100


def test_single_video_gate_on_duration_mismatch(env):
  env.media_dur = {f"{TOPIC}/ep3.mp4": 130.0}
  env.script_dur = {f"{TOPIC}/Plowing 2.funscript": 2972.0}
  r = run_topic(env, TOPIC, {
      "ep3.mp4": b"v",
      "Plowing 2.funscript": fs_script([0, 2972000]),
  })
  row = by_stem(r, "Plowing 2")
  assert row["status"] == UNMATCHED
  assert "时长对不上" in row["note"]


def test_single_video_fallback_without_duration(env):
  # 脚本探不到时长（空 actions）+ 帖内唯一视频 -> 兜底配
  r = run_topic(env, TOPIC, {
      "only.mp4": b"v",
      "whatever.funscript": json.dumps({"actions": []}).encode(),
  })
  assert by_stem(r, "whatever")["method"] == "single-video"


def test_ambiguous_twin_durations(env):
  env.media_dur = {f"{TOPIC}/ケイ.mp4": 200.0, f"{TOPIC}/ケイ.404683.mp4": 200.0}
  env.script_dur = {f"{TOPIC}/Kay.funscript": 200.2}
  r = run_topic(env, TOPIC, {
      "ケイ.mp4": b"a" * 100,
      "ケイ.404683.mp4": b"b" * 200,
      "Kay.funscript": fs_script([0, 200200]),
  })
  assert by_stem(r, "Kay")["status"] == AMBIGUOUS


def test_audio_fallback_for_asmr_package(env):
  r = run_topic(env, TOPIC, {
      "track02.wav": b"a" * 100,
      "track02.funscript": fs_script([0, 999]),
  })
  row = by_stem(r, "track02")
  assert row["status"] == PAIRED and row["target_pool"] == "audio"
  assert row["method"] == "audio:exact"


def test_unmatched_when_no_media_at_all(env):
  r = run_topic(env, TOPIC, {"solo.funscript": fs_script([0, 999])})
  assert by_stem(r, "solo")["status"] == UNMATCHED


def test_duration_verification_marks(env):
  env.media_dur = {f"{TOPIC}/X.mp4": 100.0}
  env.script_dur = {f"{TOPIC}/X.funscript": 99.0}
  r = run_topic(env, TOPIC, {"X.mp4": b"v", "X.funscript": fs_script([0, 99000])})
  assert by_stem(r, "X")["dur_mark"] == "dur✓"


# ---- provenance 救援层 ----

def test_provenance_rescues_ambiguous_twin(env):
  # Kay/Kay2 形态：双胞胎等时长，dur 探并列归 ambiguous -> 出处共位裁决
  env.media_dur = {f"{TOPIC}/ケイ.mp4": 200.0, f"{TOPIC}/ケイ.404683.mp4": 200.0}
  env.script_dur = {f"{TOPIC}/Kay.funscript": 200.2}
  r = run_topic(env, TOPIC, {
      "ケイ.mp4": b"a" * 100,
      "ケイ.404683.mp4": b"b" * 200,
      "Kay.funscript": fs_script([0, 200200]),
  }, provenance={f"{TOPIC}/Kay.funscript": f"{TOPIC}/ケイ.404683.mp4"})
  row = by_stem(r, "Kay")
  assert row["status"] == PAIRED and row["method"] == "provenance"
  pool = r["pools"]["video"]
  assert pool[row["target_cid"]]["rel"] == f"{TOPIC}/ケイ.404683.mp4"
  assert r["ambiguous"] == []


def test_provenance_rescues_unmatched_with_normal_offset(env):
  # 脚本末动作早于片尾 13s：single 闸门拦下（>10s），共位照救（时长降级为验证）
  env.media_dur = {f"{TOPIC}/full-cut.mp4": 105.0, f"{TOPIC}/other.mp4": 300.0}
  env.script_dur = {f"{TOPIC}/ローマ字.funscript": 92.0}
  r = run_topic(env, TOPIC, {
      "full-cut.mp4": b"a" * 100,
      "other.mp4": b"b" * 200,
      "ローマ字.funscript": fs_script([0, 92000]),
  }, provenance={f"{TOPIC}/ローマ字.funscript": f"{TOPIC}/full-cut.mp4"})
  row = by_stem(r, "ローマ字")
  assert row["status"] == PAIRED and row["method"] == "provenance"
  assert "dur✗" in row["dur_mark"]      # 大偏差保留配对但降置信


def test_provenance_never_overrides_name_layer(env):
  # 名字层 exact 已配上 -> 出处指向别的媒体也不翻转（幂等重跑零翻转）
  env.media_dur = {f"{TOPIC}/X.mp4": 100.0, f"{TOPIC}/Y.mp4": 100.0}
  r = run_topic(env, TOPIC, {
      "X.mp4": b"a" * 100,
      "Y.mp4": b"b" * 200,
      "X.funscript": fs_script([0, 99000]),
  }, provenance={f"{TOPIC}/X.funscript": f"{TOPIC}/Y.mp4"})
  row = by_stem(r, "X")
  assert row["status"] == PAIRED and row["method"] == "exact"
  assert r["pools"]["video"][row["target_cid"]]["rel"] == f"{TOPIC}/X.mp4"


def test_provenance_gate_script_longer_than_media(env):
  # 单向闸门：脚本 300s 显著长于媒体 200s = 媒体疑似剪辑/预告，共位不硬配
  env.media_dur = {f"{TOPIC}/cut.mp4": 200.0, f"{TOPIC}/other.mp4": 400.0}
  env.script_dur = {f"{TOPIC}/S.funscript": 300.0}
  r = run_topic(env, TOPIC, {
      "cut.mp4": b"a" * 100,
      "other.mp4": b"b" * 200,
      "S.funscript": fs_script([0, 300000]),
  }, provenance={f"{TOPIC}/S.funscript": f"{TOPIC}/cut.mp4"})
  assert by_stem(r, "S")["status"] == UNMATCHED


def test_provenance_target_missing_or_audio(env):
  # 指向不在池内的 rel -> 无效，行为同无信号
  env.media_dur = {f"{TOPIC}/V.mp4": 100.0}
  r = run_topic(env, TOPIC, {"V.mp4": b"a", "S.funscript": fs_script([0, 100])},
                provenance={f"{TOPIC}/S.funscript": f"{TOPIC}/not-on-disk.mp4"})
  assert by_stem(r, "S")["method"] == "single-video"    # 回落正常兜底
  # 指向音频池 -> target_pool 跟着走（脚本名与 wav 名对不上，名字层全空）
  r = run_topic(env, TOPIC, {
      "V.mp4": b"a",
      "track02.wav": b"c" * 10,
      "DLsite 版.funscript": fs_script([0, 999]),
  }, provenance={f"{TOPIC}/DLsite 版.funscript": f"{TOPIC}/track02.wav"})
  row = by_stem(r, "DLsite 版")
  assert row["status"] == PAIRED and row["method"] == "provenance"
  assert row["target_pool"] == "audio"
