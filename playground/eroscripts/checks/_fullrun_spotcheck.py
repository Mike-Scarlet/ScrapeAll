
import json, os, sqlite3, subprocess

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
_DB = os.path.join(_ROOT, "data", "eroscripts.db")
FFPROBE = r"E:\Program Files\ffmpeg\bin\ffprobe.exe"
SRC, DST = r"J:\es_scrape", r"J:\es_norm"


def probe(p):
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", p],
        capture_output=True, text=True)
    if r.returncode:
        return None
    j = json.loads(r.stdout)
    v = next((s for s in j["streams"]
              if s.get("codec_type") == "video"
              and s.get("disposition", {}).get("attached_pic") != 1), None)
    a = next((s for s in j["streams"]
              if s.get("codec_type") == "audio"), None)
    return {"dur": float(j["format"]["duration"]),
            "v": (v.get("codec_name"), v.get("width"), v.get("height"))
                 if v else None,
            "a": a.get("codec_name") if a else None}


con = sqlite3.connect(_DB); con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT topic_id, target_path, source_path, action FROM EroNorm "
    "WHERE action LIKE 'scale%' ORDER BY topic_id").fetchall()
con.close()
print(f"转码行总数 {len(rows)}；按档位抽 8 个核验：\n")

# 每个不同 scale 档位取一个 + 960:540 多取几个，凑 8
by_action = {}
for r in rows:
    by_action.setdefault(r["action"], []).append(r)
sample = []
for act, lst in sorted(by_action.items()):
    sample.append(lst[len(lst) // 2])          # 每档取中位一个
for r in by_action.get("scale=960:540", [])[::25][:4]:
    if r not in sample:
        sample.append(r)

bad = 0
for r in sample[:8]:
    tgt = os.path.join(DST, r["target_path"].replace("/", os.sep))
    src = os.path.join(SRC, r["source_path"].replace("/", os.sep))
    pt, ps = probe(tgt), probe(src)
    w, h = (pt["v"][1], pt["v"][2]) if pt and pt["v"] else (0, 0)
    ok_dim = pt and pt["v"] and w % 2 == 0 and h % 2 == 0 \
        and max(w, h) <= 1500
    ok_dur = pt and ps and abs(pt["dur"] - ps["dur"]) < 2.0
    ok_codec = pt and pt["v"] and pt["v"][0] == "h264"
    flag = "OK " if (ok_dim and ok_dur and ok_codec) else "BAD"
    if flag == "BAD":
        bad += 1
    print(f"[{flag}] {r['topic_id']}  {r['action']}")
    print(f"      {os.path.basename(tgt)[:60]}")
    print(f"      源 {ps['v']} {ps['dur']:.1f}s 音轨={ps['a']}"
          f"  ->  目标 {pt['v']} {pt['dur']:.1f}s 音轨={pt['a']}"
          f"  h264={'Y' if ok_codec else 'N'} 时长差={abs(pt['dur']-ps['dur']):.2f}s")
print(f"\n结果：{len(sample[:8])} 抽 {bad} 异常")
