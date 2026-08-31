import json
import os

import pytest

from scrape_all.downloader.fsutil import url_token
from scrape_all.sites.eroscripts.normalize import (
    LibraryNormalizer, classify_script_stem, pick_primary, transcode_plan,
)
from scrape_all.sites.eroscripts.pairing import PAIRED
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroExtract, EroLink, EroNorm, EroTopicItem

TOPIC = 307002
OTHER = 309999


def make_store(tmp_path):
  return TopicStore(str(tmp_path / "ero.db"))


def add_topic(store, tid, links):
  store.db.InsertRecord(EroTopicItem(
      topic_id=tid, url=f"https://discuss.eroscripts.com/t/x/{tid}",
      title="t", stat=3,
      links_json=json.dumps([{"url": u} for u in links]),
      first_seen=0.0, last_seen=0.0), on_conflict="OR REPLACE")
  store.db.Commit()


def add_erolink(store, url, dl_path, kind="media", tid=TOPIC):
  store.db.InsertRecord(EroLink(
      url=url, host="pixeldrain.com", kind=kind, dl_status="downloaded",
      dl_path=dl_path, dl_size=1, first_topic_id=tid))
  store.db.Commit()


def fs_script(actions=None):
  return json.dumps({"actions": [{"at": a, "pos": 0}
                                 for a in (actions or [0, 99000])]}).encode()


@pytest.fixture
def env(tmp_path):
  src = tmp_path / "scrape"
  dst = tmp_path / "norm"
  (src / str(TOPIC)).mkdir(parents=True)
  store = make_store(tmp_path)
  add_topic(store, TOPIC, [])

  probe_map: dict[str, dict] = {}
  calls: list[list[str]] = []

  def probe(path):
    return probe_map.get(path) or probe_map.get(os.path.normcase(path)) \
        or probe_map.get("__default__")

  def run_ffmpeg(args, timeout):
    calls.append(list(args))
    out = args[-1]
    if "-c:a" in args and args[args.index("-c:a") + 1] == "copy" and \
        probe_map.get("__copy_fails__"):
      return 1, "copy refused"
    with open(out, "wb") as f:
      f.write(b"TRANSCODED")
    return 0, ""

  env.src, env.dst, env.store = src, dst, store
  env.probe_map, env.calls = probe_map, calls
  env.probe, env.run_ffmpeg = probe, run_ffmpeg
  env.norm = LibraryNormalizer(
      store, str(src), str(dst), emit=lambda line: None,
      run_ffmpeg=run_ffmpeg, probe=probe)
  return env


def put(env, rel, data: bytes):
  p = env.src / rel.replace("/", os.sep)
  p.parent.mkdir(parents=True, exist_ok=True)
  p.write_bytes(data)
  return rel


def dst_exists(env, rel):
  return (env.dst / rel.replace("/", os.sep)).exists()


def norm_rows(env):
  return {r.target_path: r for r in env.store.db.QueryRecords(EroNorm)}


# ---- 纯函数 ----

def test_classify_script_stem():
  c = classify_script_stem("X (Less Vibrations).pitch")
  assert c["axis"] == "pitch" and c["tagged"]
  assert classify_script_stem("X")["tagged"] is False


def test_pick_primary_plain_wins():
  sel = pick_primary(["X", "X (Less Vibrations)", "X (Handy 2 PRO Overclocked)",
                      "X.pitch"])
  assert sel["primary"]["stem"] == "X"
  assert [a["stem"] for a in sel["axis"]] == ["X.pitch"]
  assert sorted(v["stem"] for v in sel["variants"]) == \
      ["X (Handy 2 PRO Overclocked)", "X (Less Vibrations)"]


def test_pick_primary_priority_table():
  sel = pick_primary(["X (Less Vibrations)", "X (Handy 2 PRO Overclocked)"],
                     ["handy 2 pro"])
  assert sel["primary"]["stem"] == "X (Handy 2 PRO Overclocked)"
  assert [v["stem"] for v in sel["variants"]] == ["X (Less Vibrations)"]


def test_pick_primary_priority_table_arbitrates_multi_plain():
  # Hard/Soft 这类平级平凡脚本：同样吃优先级表（表序先到先得），无命中才挂起
  sel = pick_primary(["Hard fap-hero", "Soft fap-hero"], ["soft"])
  assert sel["primary"]["stem"] == "Soft fap-hero"
  assert [v["stem"] for v in sel["variants"]] == ["Hard fap-hero"]
  assert pick_primary(["Hard fap-hero", "Soft fap-hero"],
                      [])["pending"]      # 显式空表才挂起（默认吃生产表）


def test_pick_primary_priority_shortest_wins_on_tie():
  # 同一子串命中多个候选 -> 取最短 stem（平凡版是变体版子串的场景）
  sel = pick_primary(["(Stronger End) Sherry Birkin", "Sherry Birkin"],
                     ["sherry birkin"])
  assert sel["primary"]["stem"] == "Sherry Birkin"
  assert [v["stem"] for v in sel["variants"]] == \
      ["(Stronger End) Sherry Birkin"]


def test_pick_primary_pending_cases():
  assert pick_primary(["X (A)", "X (B)"])["pending"]          # 同base全带标签，表无命中
  assert pick_primary(["X", "Y"])["pending"]                  # 多个平凡且无前缀关系
  assert pick_primary(["X.pitch"])["pending"]                 # 只有轴脚本
  assert not pick_primary(["X (A)"], ["a"])["pending"]        # 表命中


def test_pick_primary_single_tagged_script_is_primary():
  # Iwara "[Source]" / "[Chussy]" 署名尾巴：单脚本组它就是主，不挂起
  sel = pick_primary(["Iwara - Some Video [abc123] [Source]"])
  assert sel["primary"]["stem"] == "Iwara - Some Video [abc123] [Source]"
  assert not sel["pending"]


def test_pick_primary_prefix_normalization():
  # _hand / FAST / .raw 形态：最短平凡是基名，其余归变体
  sel = pick_primary(["女の子", "女の子_hand", "女の子_handFocus",
                      "女の子_withTwist", "女の子.twist"])
  assert sel["primary"]["stem"] == "女の子"
  assert [a["stem"] for a in sel["axis"]] == ["女の子.twist"]
  assert sorted(v["stem"] for v in sel["variants"]) == \
      ["女の子_hand", "女の子_handFocus", "女の子_withTwist"]
  sel = pick_primary(["X", "X.raw", "X.pitch", "X.surge"])
  assert sel["primary"]["stem"] == "X"
  assert sorted(v["stem"] for v in sel["variants"]) == ["X.raw"]


def test_pick_primary_tagged_base_with_abbrev_axes():
  # Iwara 基名尾随 [Source]（带标签）+ .p/.s/.t 缩写轴：基名仍是主
  base = "Iwara - Some Vid [abc] [Source]"
  sel = pick_primary([base, base + ".p", base + ".s", base + ".t"])
  assert sel["primary"]["stem"] == base
  assert sorted(v["stem"] for v in sel["variants"]) == \
      [base + ".p", base + ".s", base + ".t"]


def test_transcode_plan():
  # 两边都 ≤1500 copy：贴线（恰好 1500）也不动
  assert transcode_plan({"width": 1500, "height": 1000}) == (False, None)
  assert transcode_plan({"width": 1280, "height": 720}) == (False, None)
  assert transcode_plan({"width": 1000, "height": 1500}) == (False, None)
  # 任一边超 1500 -> 2 的整数次幂对半除，宽高整除后取偶（atplayer 同款）
  assert transcode_plan({"width": 1920, "height": 1080}) == \
      (True, "scale=960:540")                       # 1.28x -> ÷2
  assert transcode_plan({"width": 2560, "height": 1440}) == \
      (True, "scale=1280:720")                      # 1.71x -> ÷2
  assert transcode_plan({"width": 2000, "height": 1500}) == \
      (True, "scale=1000:750")                      # 1.33x -> ÷2（4:3）
  assert transcode_plan({"width": 3840, "height": 2160}) == \
      (True, "scale=960:540")                       # 2.56x -> ÷4
  assert transcode_plan({"width": 2160, "height": 3840}) == \
      (True, "scale=540:960")                       # 纵向 4K -> ÷4
  assert transcode_plan({"width": 7680, "height": 3840}) == \
      (True, "scale=960:480")                       # 5.12x -> ÷8
  # 整除出奇数 -> 取偶（round(x/2)*2）
  assert transcode_plan({"width": 1999, "height": 1125}) == \
      (True, "scale=1000:562")
  assert transcode_plan(None) == (False, None)


# ---- 端到端 ----

def test_copy_end_to_end(env):
  put(env, f"{TOPIC}/V.mp4", b"v" * 1000)
  put(env, f"{TOPIC}/V.funscript", fs_script())
  env.probe_map[str(env.src / str(TOPIC) / "V.mp4")] = {
      "duration": 99.0, "width": 1280, "height": 720, "long_edge": 1280}
  totals = env.norm.run(execute=True)
  assert totals["copied"] == 2 and totals["transcoded"] == 0
  assert dst_exists(env, f"{TOPIC}/V.mp4") and dst_exists(env, f"{TOPIC}/V.funscript")
  rows = norm_rows(env)
  assert rows[f"{TOPIC}/V.mp4"].action == "copy"
  assert rows[f"{TOPIC}/V.mp4"].kind == "video"
  assert rows[f"{TOPIC}/V.funscript"].kind == "script"
  assert env.calls == []          # ≤1080 不碰 ffmpeg


def test_transcode_end_to_end_with_audio_copy_fallback(env):
  src = str(env.src / str(TOPIC) / "V.mp4")
  out = str(env.dst / str(TOPIC) / "V.mp4")
  env.probe_map[src] = {"duration": 100.0, "width": 3840,
                        "height": 2160, "long_edge": 3840}
  env.probe_map["__copy_fails__"] = True       # -c:a copy 失败 -> 回退 aac
  env.probe_map["__default__"] = {"duration": 100.0}
  put(env, f"{TOPIC}/V.mp4", b"v" * 100)
  put(env, f"{TOPIC}/V.funscript", fs_script())
  totals = env.norm.run(execute=True)
  assert totals["transcoded"] == 1
  assert len(env.calls) == 2                    # copy 尝试 + aac 回退
  assert env.calls[0][env.calls[0].index("-c:a") + 1] == "copy"
  assert env.calls[1][env.calls[1].index("-c:a") + 1] == "aac"
  assert "scale=960:540" in env.calls[0]    # 3840x2160 对半除 ÷4
  assert norm_rows(env)[f"{TOPIC}/V.mp4"].action.startswith("scale")
  assert dst_exists(env, f"{TOPIC}/V.mp4")


def test_variants_and_axis_layout(env):
  put(env, f"{TOPIC}/X.mp4", b"v" * 100)
  put(env, f"{TOPIC}/X.funscript", fs_script())
  put(env, f"{TOPIC}/X.pitch.funscript", fs_script())
  put(env, f"{TOPIC}/X (Less Vibrations).funscript", fs_script())
  env.probe_map["__default__"] = {"duration": 99.0, "width": 640,
                                  "height": 360, "long_edge": 640}
  env.norm.run(execute=True)
  assert dst_exists(env, f"{TOPIC}/X.mp4")
  assert dst_exists(env, f"{TOPIC}/X.funscript")
  assert dst_exists(env, f"{TOPIC}/X.pitch.funscript")
  assert dst_exists(env, f"{TOPIC}/variants/X (Less Vibrations).funscript")
  rows = norm_rows(env)
  assert rows[f"{TOPIC}/X.pitch.funscript"].kind == "axis-script"
  assert rows[f"{TOPIC}/variants/X (Less Vibrations).funscript"].kind == \
      "variant-script"


def test_pending_group_emits_nothing(env):
  # 双变体组（同 base 全带标签）无优先级表 -> 挂起不落位
  put(env, f"{TOPIC}/Y.mp4", b"v" * 100)
  put(env, f"{TOPIC}/Y (Less Vibrations).funscript", fs_script())
  put(env, f"{TOPIC}/Y (Handy 2 PRO Overclocked).funscript", fs_script())
  env.probe_map["__default__"] = {"duration": 99.0, "width": 640,
                                  "height": 360, "long_edge": 640}
  totals = env.norm.run(execute=True)
  assert totals["pending_groups"] == 1 and totals["copied"] == 0
  assert not dst_exists(env, f"{TOPIC}/Y.mp4")
  assert norm_rows(env) == {}
  # 填上优先级表重跑 -> 组解挂落位，表首选主
  env.norm.priority = ["handy 2 pro"]
  totals = env.norm.run(execute=True)
  assert totals["pending_groups"] == 0 and totals["copied"] == 3
  assert dst_exists(env, f"{TOPIC}/Y (Handy 2 PRO Overclocked).mp4")
  assert dst_exists(env, f"{TOPIC}/variants/Y (Less Vibrations).funscript")


def test_idempotent_rerun_skips(env):
  put(env, f"{TOPIC}/V.mp4", b"v" * 1000)
  put(env, f"{TOPIC}/V.funscript", fs_script())
  env.probe_map["__default__"] = {"duration": 99.0, "width": 640,
                                  "height": 360, "long_edge": 640}
  t1 = env.norm.run(execute=True)
  n_calls = len(env.calls)
  t2 = env.norm.run(execute=True)
  assert t2["skip"] == t1["files"] and t2["copied"] == 0
  assert len(env.calls) == n_calls


def test_external_dir_pool_via_erolink(env):
  # gofile 文件夹链接：dl_path 只记目录，目录在他帖名下
  put(env, f"{OTHER}/Rebirth 1.mp4", b"v" * 100)
  put(env, f"{OTHER}/Kimiko.mp4", b"k" * 100)
  put(env, f"{TOPIC}/Rebirth 1.funscript", fs_script())
  add_topic(env.store, TOPIC, ["https://gofile.io/d/XX"])
  add_erolink(env.store, "https://gofile.io/d/XX", f"{OTHER}", kind="media")
  env.probe_map["__default__"] = {"duration": 99.0, "width": 640,
                                  "height": 360, "long_edge": 640}
  env.norm.run(execute=True)
  assert dst_exists(env, f"{TOPIC}/Rebirth 1.mp4")
  assert not dst_exists(env, f"{TOPIC}/Kimiko.mp4")   # 同目录其他文件不硬塞


def test_same_stem_groups_token_apart(env):
  # 两个组主脚本 stem 相同（不同源不同时长）-> 媒体目标撞名，第二把 token
  put(env, f"{TOPIC}/a/V.mp4", b"1" * 100)
  put(env, f"{TOPIC}/b/V.mp4", b"2" * 300)
  put(env, f"{TOPIC}/a/A.funscript", fs_script())               # 99s
  put(env, f"{TOPIC}/b/A.funscript", fs_script([0, 200000]))    # 200s，同 stem 不同体积
  env.probe_map[str(env.src / str(TOPIC) / "a" / "V.mp4")] = {
      "duration": 99.0, "width": 640, "height": 360, "long_edge": 640}
  env.probe_map[str(env.src / str(TOPIC) / "b" / "V.mp4")] = {
      "duration": 200.0, "width": 640, "height": 360, "long_edge": 640}
  env.norm.run(execute=True)
  files = sorted(os.listdir(env.dst / str(TOPIC)))
  medias = [f for f in files if f.endswith(".mp4")]
  assert len(medias) == 2 and "A.mp4" in medias        # a 组先落占住原名
  other = next(f for f in medias if f != "A.mp4")
  assert url_token(f"{TOPIC}/b/V.mp4") in other        # b 组媒体源 token 第二把


def test_video_probe_missing_pends_group(env):
  put(env, f"{TOPIC}/Z.mp4", b"v" * 100)
  put(env, f"{TOPIC}/Z.funscript", fs_script())
  # probe_map 空 -> probe 返回 None -> 组挂起不落位
  totals = env.norm.run(execute=True)
  assert totals["pending_groups"] == 1 and totals["copied"] == 0
  assert norm_rows(env) == {}


# ---- provenance 救援 ----

def _set_links(env, entries):
  """重写 TOPIC links_json（含 kind/section/post_number 的完整条目）"""
  env.store.db.InsertRecord(EroTopicItem(
      topic_id=TOPIC, url=f"https://discuss.eroscripts.com/t/x/{TOPIC}",
      title="t", stat=3, links_json=json.dumps(entries),
      first_seen=0.0, last_seen=0.0), on_conflict="OR REPLACE")
  env.store.db.Commit()


def test_provenance_external_twin_end_to_end(env):
  # Kay2 形态：帖内无媒体，双胞胎视频全在他帖目录且等时长（dur 层并列
  # 歧义）；楼层共位（post1 脚本+ケイ.mp4、post2 只有另一个双胞胎）裁决
  put(env, f"{OTHER}/ケイ.mp4", b"a" * 100)
  put(env, f"{OTHER}/ケイ.404683.mp4", b"b" * 200)
  put(env, f"{TOPIC}/Kay2.funscript", fs_script([0, 200200]))
  add_erolink(env.store, "https://s/Kay2.funscript", f"{TOPIC}/Kay2.funscript")
  add_erolink(env.store, "https://v/404681", f"{OTHER}/ケイ.mp4")
  add_erolink(env.store, "https://v/404683", f"{OTHER}/ケイ.404683.mp4")
  _set_links(env, [
      {"url": "https://s/Kay2.funscript", "kind": "script",
       "section": "Script", "post_number": 1},
      {"url": "https://v/404681", "kind": "source",
       "section": "Source", "post_number": 1},
      {"url": "https://v/404683", "kind": "source",
       "section": "Source", "post_number": 2},
  ])
  env.probe_map["__default__"] = {"duration": 200.0, "width": 640,
                                  "height": 360, "long_edge": 640}
  totals = env.norm.run(execute=True)
  assert totals["ambiguous"] == 0 and totals["unmatched"] == 0
  assert dst_exists(env, f"{TOPIC}/Kay2.mp4")
  assert dst_exists(env, f"{TOPIC}/Kay2.funscript")
  rows = norm_rows(env)
  assert rows[f"{TOPIC}/Kay2.mp4"].source_path == f"{OTHER}/ケイ.mp4"
  assert not dst_exists(env, f"{TOPIC}/Kay2.404683.mp4")   # 双胞胎不误配


def test_provenance_requires_script_section(env):
  # 交叉引用楼层（section=''）不带模板意图 -> 不出手，歧义留给人工
  put(env, f"{OTHER}/ケイ.mp4", b"a" * 100)
  put(env, f"{OTHER}/ケイ.404683.mp4", b"b" * 200)
  put(env, f"{TOPIC}/Kay2.funscript", fs_script([0, 200200]))
  add_erolink(env.store, "https://s/Kay2.funscript", f"{TOPIC}/Kay2.funscript")
  add_erolink(env.store, "https://v/404681", f"{OTHER}/ケイ.mp4")
  add_erolink(env.store, "https://v/404683", f"{OTHER}/ケイ.404683.mp4")
  _set_links(env, [
      {"url": "https://s/Kay2.funscript", "kind": "script",
       "section": "", "post_number": 1},
      {"url": "https://v/404681", "kind": "source",
       "section": "Source", "post_number": 1},
      {"url": "https://v/404683", "kind": "source",
       "section": "Source", "post_number": 2},
  ])
  env.probe_map["__default__"] = {"duration": 200.0, "width": 640,
                                  "height": 360, "long_edge": 640}
  totals = env.norm.run(execute=True)
  assert totals["ambiguous"] == 1 and totals["copied"] == 0
  assert not dst_exists(env, f"{TOPIC}/Kay2.mp4")


def test_provenance_multi_script_axis_pack(env):
  # 330402 形态：同楼层 6+1 脚本共指一个视频（名字 slug 对不上、时长差
  # 156s 超 single 闸门）-> 全组配对，主+轴落位
  put(env, f"{TOPIC}/少女彈珠汽水 7.mp4", b"v" * 100)
  put(env, f"{TOPIC}/407591-480p.funscript", fs_script([0, 743000]))
  put(env, f"{TOPIC}/407591-480p.pitch.funscript", fs_script([0, 743000]))
  add_erolink(env.store, "https://s/a.funscript", f"{TOPIC}/407591-480p.funscript")
  add_erolink(env.store, "https://s/p.funscript",
              f"{TOPIC}/407591-480p.pitch.funscript")
  add_erolink(env.store, "https://v/407591", f"{TOPIC}/少女彈珠汽水 7.mp4")
  _set_links(env, [
      {"url": "https://s/a.funscript", "kind": "script",
       "section": "Script", "post_number": 1},
      {"url": "https://s/p.funscript", "kind": "script",
       "section": "Script", "post_number": 1},
      {"url": "https://v/407591", "kind": "source",
       "section": "Source", "post_number": 1},
  ])
  env.probe_map["__default__"] = {"duration": 899.0, "width": 640,
                                  "height": 360, "long_edge": 640}
  totals = env.norm.run(execute=True)
  assert totals["unmatched"] == 0 and totals["pending_groups"] == 0
  assert dst_exists(env, f"{TOPIC}/407591-480p.mp4")
  assert dst_exists(env, f"{TOPIC}/407591-480p.funscript")
  assert dst_exists(env, f"{TOPIC}/407591-480p.pitch.funscript")
  rows = norm_rows(env)
  assert rows[f"{TOPIC}/407591-480p.pitch.funscript"].kind == "axis-script"


def test_provenance_resolves_archive_and_dir(env):
  # URL 解析三形态：脚本 URL 是压缩包（EroExtract 反查）、媒体 URL 是
  # gofile 目录（walk 单文件）
  put(env, f"{TOPIC}/pack.zip", b"PK")
  put(env, f"{TOPIC}/pack/X.funscript", fs_script([0, 85000]))
  put(env, f"{OTHER}/folder/M.mp4", b"v" * 100)
  add_erolink(env.store, "https://s/pack.zip", f"{TOPIC}/pack.zip")
  add_erolink(env.store, "https://gofile.io/d/XX", f"{OTHER}/folder",
              kind="media")
  env.store.db.InsertRecord(EroExtract(
      archive_path=f"{TOPIC}/pack.zip", topic_id=TOPIC, status="done",
      depth=1, files_json=json.dumps(
          [{"path": f"{TOPIC}/pack/X.funscript", "size": 1,
            "src": "X.funscript", "action": "wrote"}])), on_conflict="OR REPLACE")
  env.store.db.Commit()
  _set_links(env, [
      {"url": "https://s/pack.zip", "kind": "script",
       "section": "Script", "post_number": 1},
      {"url": "https://gofile.io/d/XX", "kind": "media",
       "section": "Source", "post_number": 1},
  ])
  env.probe_map["__default__"] = {"duration": 100.0, "width": 640,
                                  "height": 360, "long_edge": 640}
  totals = env.norm.run(execute=True)
  assert totals["unmatched"] == 0
  assert dst_exists(env, f"{TOPIC}/X.mp4")
  assert dst_exists(env, f"{TOPIC}/X.funscript")
