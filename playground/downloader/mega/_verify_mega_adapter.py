
"""mega adapter 验证轮（固定清单，无遍历）。

  1) 探活 6 条已知链接（3 死 + 3 活）—— 6 次页面加载，只读
  2) 幂等：已下载的 isami_ride.mp4 应 skipped 零流量 —— 1 次页面加载
  3) adapter 真实下载：J1tViZLa folder ZIP（37.15MB）落盘 + 解压校验
     —— 1 次页面加载 + 37MB

共 8 次页面加载 + 1 次 37MB 下载。"""
import asyncio
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.downloader.adapters import adapter_for
from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_VERIFY = os.path.join(_ROOT, "data", "eroscripts", "files", "_verify")

PROBE_LIST = [
    # 3 死（观察轮已确认）
    "https://mega.nz/file/Lj43zSwJ#YPDytvHKOPLU_bRHt-TgPg0Saml4pwVGsdSXXfRMegY",
    "https://mega.nz/folder/z0JzVIAY#mE2-P2BCbe5i1KjyZ8YfiQ",
    "https://mega.nz/folder/fQEkyQqD#lBWTORFB9Nrl1SRLXvyllA",
    # 3 活（批次二确认）
    "https://mega.nz/file/mh4QhYLZ#ScK1HkZbBymamt6dPfIipHicde4qNTRS17rsCHFMSrw",
    "https://mega.nz/folder/J1tViZLa#LSBfQTWLTuGXnuStQmSHvA",
    "https://mega.nz/folder/hS0XmIgL#afw2rN0BPH9pURsw7kIeTw",
]
IDEMPOTENT_DL = "https://mega.nz/file/7hB2WbaD#KuV2r-Wa9CuaZXYEdW93na8vDTzGIqvuV6IbFBpgxt4"
REAL_DL = "https://mega.nz/folder/J1tViZLa#LSBfQTWLTuGXnuStQmSHvA"


async def main():
  adapter = adapter_for("https://mega.nz/file/x#k")
  async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:

    print("== 1) 探活 6 条已知链接")
    for u in PROBE_LIST:
      p = await adapter.probe(engine, u)
      files_note = f" files={len(p.files)}" if p.files else ""
      print(f"   {u.rsplit('/', 1)[-1][:28]:30s} -> {p.status:6s} "
            f"name={p.filename!r} size={p.size}{files_note} {p.note}")

    print("== 2) 幂等（isami_ride.mp4 已在盘上 -> skipped 零流量）")
    r = await adapter.download(engine, IDEMPOTENT_DL, _VERIFY)
    print(f"   -> {r.status} path={r.path} {r.note}")

    print("== 3) adapter 真实下载 J1tViZLa folder ZIP（37.15MB）")
    r = await adapter.download(engine, REAL_DL, _VERIFY)
    print(f"   -> {r.status} size={r.size:,} path={r.path} {r.note}")
    if r.status == "downloaded" and r.path and r.path.endswith(".zip"):
      with zipfile.ZipFile(r.path) as zf:
        bad = zf.testzip()
        print(f"   zip 完整性: {'OK' if bad is None else f'损坏: {bad}'}，"
              f"{len(zf.namelist())} 个条目")
        total = 0
        for i in zf.infolist():
          total += i.file_size
          print(f"      {i.file_size:>12,}  {i.filename}")
        print(f"   解压总字节: {total:,}")
        main_fs = next((n for n in zf.namelist()
                        if n.endswith(".funscript")
                        and not n.endswith((".pitch.funscript", ".roll.funscript",
                                            ".surge.funscript", ".sway.funscript",
                                            ".twist.funscript"))), None)
        if main_fs:
          data = json.loads(zf.read(main_fs))
          print(f"   主 funscript 合法 JSON，actions={len(data.get('actions') or [])}，"
                f"版本={data.get('version')}")

    print("\n完成，3s 后关浏览器")
    await asyncio.sleep(3)


asyncio.run(main())
