# 只读：320427 新件校验——魔数/本地头 vs 中央目录一致性（串包特征复查）/条目与体积
import os
import struct
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEST = r"J:\es_scrape"
P = os.path.join(DEST, "320427", "【KK VR180】2000フォロワー感謝 長風 长风 Changfeng 8K60FPS.zip")

size = os.path.getsize(P)
print(f"盘上体积: {size:,}B（坏件当时 1,847,950,791B，同量级即正常）")

with open(P, "rb") as f:
    data = f.read(4096)
print(f"魔数: {data[:4]!r}  {'OK' if data[:4] == b'PK\x03\x04' else '!! 不是 zip'}")
local_name = ""
if data[:4] == b"PK\x03\x04":
    nlen, elen = struct.unpack("<HH", data[26:30])
    local_name = data[30:30 + nlen].decode("utf-8", "replace")
    print(f"首本地头文件名: {local_name}")

with zipfile.ZipFile(P) as z:
    infos = z.infolist()
    print(f"中央目录条目: {len(infos)}")
    total = 0
    for i in infos:
        total += i.file_size
        print(f"  {i.filename}  {i.file_size:,}B  offset={i.header_offset:,}")
    print(f"解压后合计: {total:,}B")
    cent_name = infos[0].filename if infos else ""
    head = cent_name.split("/", 1)[-1] if "/" in cent_name else cent_name
    ok = local_name.endswith(head) or head in local_name or local_name == cent_name
    print(f"本地头与中央目录一致: {'OK' if ok else '!! 不一致（串包特征）'}")
