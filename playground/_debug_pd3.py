
"""pixeldrain 联调 v3：小文件端到端 + 活列表 API 验证（省配额版）。

  1) /api/list/dQotgt6u（已确认活）：JSON 是否可用、文件清单结构
  2) Range 探一批库内 /u|/d 文件链接（每条 1 字节），挑 <= 20MB 的活链
  3) 对挑中的小文件走 direct_download 真下载到 _verify，校验大小
"""
import asyncio
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

SMALL_CAP = 20 * 1024 * 1024
_PROBE_BATCH = 12

DL_URL = "https://pixeldrain.com/api/file/{id}?download"


def db_file_links():
  con = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(
      os.path.abspath(__file__))), "data", "eroscripts.db"))
  seen, out = set(), []
  for (lj,) in con.execute(
      "SELECT links_json FROM EroTopicItem WHERE stat=2"):
    for l in json.loads(lj):
      u = l["url"]
      if u not in seen and "pixeldrain.com" in u and "/l/" not in u:
        seen.add(u)
        out.append(u)
  con.close()
  return out


async def main():
  files_dir = os.path.join(os.path.dirname(os.path.dirname(
      os.path.abspath(__file__))), "data", "eroscripts", "files", "_verify")
  os.makedirs(files_dir, exist_ok=True)
  async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:

    # 1) 活列表的 API JSON
    r = await engine.fetch_json("https://pixeldrain.com/api/list/dQotgt6u",
                                park_url="https://pixeldrain.com/")
    if r.get("status") == 200 and r.get("body"):
      b = r["body"]
      files = b.get("files") or []
      print(f"[1] 活列表 API OK: title={b.get('title')!r} files={len(files)}")
      for f in files[:3]:
        print(f"    - {f.get('name')} size={f.get('size')} id={f.get('id')}")
    else:
      print(f"[1] 活列表 API 不可用: {r}")

    # 2) Range 批量探小文件
    links = db_file_links()
    print(f"[2] 库内 pixeldrain 文件链接共 {len(links)}，探前 {_PROBE_BATCH} 条")
    small = None
    for u in links[:_PROBE_BATCH]:
      fid = u.rstrip("/").split("/")[-1]
      info = await engine.probe_headers(DL_URL.format(id=fid),
                                        park_url="https://pixeldrain.com/")
      status = info.get("status")
      if status in (200, 206):
        h = info.get("headers", {})
        cr = h.get("content-range", "")
        size = int(cr.rsplit("/", 1)[-1]) if "/" in cr else None
        name = (h.get("content-disposition") or "")[:80]
        print(f"    {u} -> alive size={size} cd={name}")
        if small is None and size and 0 < size <= SMALL_CAP:
          small = (u, fid, size)
      else:
        print(f"    {u} -> http {status}")
    if not small:
      print("[2] 没探到 <=20MB 的小文件，只验证到 probe 为止")
      return

    # 3) 小文件真下载
    u, fid, size = small
    print(f"[3] 端到端下载小文件 {u} ({size} B)")
    try:
      path = await engine.direct_download(DL_URL.format(id=fid), files_dir)
      got = os.path.getsize(path)
      print(f"[3] 落盘 {path} {got} B，与头一致: {got == size}")
    except Exception as e:
      print(f"[3] 下载失败: {e}")

    await asyncio.sleep(10)


asyncio.run(main())
