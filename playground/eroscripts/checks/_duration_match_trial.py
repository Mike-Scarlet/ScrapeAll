# 只读终验：时长匹配兜底在最难两类案例上的实测
#   A. 罗马字↔日文：307472 脚本 "Hare Kisaki" vs 视频 "キサキ【support plan ＋】"
#   B. 双视频撞名：307860 脚本 "Kay" vs ケイ.mp4 + ケイ.404683.mp4（同系列同真名两把）
#   C. 后缀变体：307720 "multi-axis"脚本 vs "(Extended)"视频；314235 "-P4-RF35" mkv
# 只读：json + ffprobe。
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEST = r"J:\es_scrape"
FFPROBE = r"E:\Program Files\ffmpeg\bin\ffprobe.EXE"


def script_last_at(path):
    data = json.load(open(path, encoding="utf-8"))
    acts = data.get("actions") or []
    return acts[-1]["at"] / 1000 if acts else None


def video_duration(path):
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


CASES = [
    ("307472", ["[Harechippai] Hare Kisaki.funscript",
                "[Harechippai] Hare Kisaki.pitch.funscript"],
     ["[Harechippai (はれ)] キサキ【support plan ＋】.mp4"]),
    ("307860", ["[Harechippai] Kay.funscript"],
     ["[Harechippai (はれ)] ケイ.404683.mp4", "[Harechippai (はれ)] ケイ.mp4"]),
    ("307720", ["[貧乳愛好会会長補佐代理見習いdustmemory2] Having lots of sex (multi-axis).funscript"],
     ["[貧乳愛好会会長補佐代理見習いdustmemory2] Having lots of sex (Extended).mp4"]),
    ("314235", ["funen gomi - 棗イロハ Natsume Iroha.funscript"],
     ["funen gomi - 棗イロハ Natsume Iroha-P4-RF35.mkv",
      "[不燃ごみ太郎] 棗イロハ【フルサイズ+各種ループ_静画】.mp4"]),
]

for tid, scripts, videos in CASES:
    print(f"--- {tid} ---")
    s_durs = []
    for sf in scripts:
        p = os.path.join(DEST, tid, sf)
        d = script_last_at(p) if os.path.exists(p) else None
        s_durs.append(d)
        print(f"  脚本 {d:8.3f}s  {sf[:70]}")
    for vf in videos:
        p = os.path.join(DEST, tid, vf)
        d = video_duration(p) if os.path.exists(p) else None
        if d is None:
            print(f"  视频 {'?':>8}    {vf[:70]}  (ffprobe 失败或不存在)")
            continue
        deltas = [f"{d - s:+.1f}s" for s in s_durs if s is not None]
        print(f"  视频 {d:8.3f}s  {vf[:70]}  对各脚本Δ: {deltas}")
