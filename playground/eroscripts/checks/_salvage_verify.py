# 只读校验：三个回捞件是否已按目标名就位、体积逐字节对上期望、funscript
# 结构合法。全部通过才打印 READY（改库步骤另行执行）。
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEST = r"J:\es_scrape"

ITEMS = [
    (r"314297\[Sanjiku] RJ01583098 - The Slutty Young Lady Is Restrained And Taught A Lesson ~Her Pride Is Shattered~ (Part.3d00110b.funscript",
     82316, True),
    (r"329965\hololive-vtuber-amane-kanata-and-i-have-sex-in-a-secret-room_720p.b540bead.funscript",
     136766, True),
    (r"324422\[貧乳愛好会会長補佐代理見習い] Loli God Requiem.499e0052.zip",
     299620706, False),
]

ok = True
for rel, expect, is_funscript in ITEMS:
    p = os.path.join(DEST, rel)
    print(f"--- {rel}")
    if not os.path.exists(p):
        print(f"  [缺失] 不在目标路径")
        ok = False
        continue
    actual = os.path.getsize(p)
    mark = "OK" if actual == expect else f"[体积不符] 期望 {expect}B"
    print(f"  体积: {actual}B  {mark}")
    if actual != expect:
        ok = False
        continue
    if is_funscript:
        try:
            data = json.load(open(p, encoding="utf-8"))
            acts = data.get("actions")
            if isinstance(acts, list) and acts:
                last = acts[-1].get("at")
                print(f"  结构: 合法 funscript，actions={len(acts)}，末尾动作 {last}ms")
            else:
                print(f"  [结构异常] 无有效 actions")
                ok = False
        except (ValueError, OSError) as e:
            print(f"  [坏JSON] {e}")
            ok = False
    else:
        with open(p, "rb") as f:
            head = f.read(4)
        print(f"  zip 头: {head!r}  {'OK' if head[:2] == b'PK' else '[非zip头]'}")
        if head[:2] != b"PK":
            ok = False

print("\nREADY" if ok else "\nNOT_READY（先别改库）")
