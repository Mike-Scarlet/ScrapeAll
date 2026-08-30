# 只读取证：320427 mega zip 损坏定性——首部本地头文件名 vs 中央目录 vs 321139 对照
import os
import struct
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEST = r"J:\es_scrape"
BIG = os.path.join(DEST, "320427", "【KK VR180】2000フォロワー感謝 長風 长风 Changfeng 8K60FPS.zip")
MIZU = os.path.join(DEST, "321139", "[見ず水煮 mizumizuni] 真紅.zip")

def head_probe(path, label):
    print(f"=== {label} ===")
    with open(path, "rb") as f:
        data = f.read(4096)
    print(f"  魔数: {data[:4]!r}")
    # 第一个本地文件头 PK\x03\x04：名长在 offset 26/28
    if data[:4] == b"PK\x03\x04":
        nlen, elen = struct.unpack("<HH", data[26:30])
        name = data[30:30 + nlen]
        print(f"  首本地头文件名: {name!r} -> {name.decode('utf-8', 'replace')}")
    # 尾部中央目录第一个条目
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        print(f"  中央目录条目数: {len(infos)}")
        for i in infos[:3]:
            print(f"    {i.filename}  {i.file_size:,}B  header_offset={i.header_offset:,}")
    return

head_probe(BIG, "320427 大 zip")
head_probe(MIZU, "321139 mizumizuni zip 对照")
# 大 zip 体积 vs 两边内容
print(f"\n320427 zip 盘上 {os.path.getsize(BIG):,}B")
with zipfile.ZipFile(MIZU) as z:
    print(f"321139 zip 条目合计 {sum(i.file_size for i in z.infolist()):,}B")
# 大 zip 前几 KB 里是否有 mizumizuni 字样散落
with open(BIG, "rb") as f:
    first1m = f.read(1024 * 1024)
print(f"320427 首 1MB 含 'mizumizuni' 字样: {b'mizumizuni' in first1m}")
