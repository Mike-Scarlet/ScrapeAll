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


def run_topic(env, tid, files):
  env.root = make_tree(env.tmp, tid, files)
  all_rels = rels(env.root, tid)
  vid = [r for r in all_rels if os.path.splitext(r)[1].lower() == ".mp4"]
  aud = [r for r in all_rels if os.path.splitext(r)[1].lower() == ".wav"]
  scr = [r for r in all_rels if r.endswith(".funscript")]
  return env.matcher.match(vid, aud, scr, fs(env.root))


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
