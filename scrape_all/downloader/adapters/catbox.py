
import os
from urllib.parse import urlsplit

from scrape_all.downloader.adapters.base import (
    DownloadResult, HostAdapter, ProbeResult, size_from_range_headers,
)
from scrape_all.downloader.fsutil import sanitize_filename

# catbox：纯直链文件（files.catbox.moe/{hash}.{ext}，litter 是限时变体域名，
# 实测 litter 子域网络层整体取不动，探活给 unknown 不误判死）。
# 无 CDN 对抗、无登录，inline 渲染（无 attachment 头），浏览器页内同源 blob
# 取回即可；文件上限 200MB，blob 路径够用。


class CatboxAdapter(HostAdapter):
  hosts = frozenset({"files.catbox.moe", "litter.catbox.moe"})

  @staticmethod
  def _filename(url: str) -> str:
    return os.path.basename(urlsplit(url).path) or "catbox_file"

  async def probe(self, engine, url: str) -> ProbeResult:
    info = await engine.probe_headers(url)
    status = info.get("status", 0)
    if status in (200, 206):
      return ProbeResult("alive", filename=self._filename(url),
                         size=size_from_range_headers(info.get("headers", {})),
                         note=f"http {status}")
    if status in (404, 410):
      return ProbeResult("dead", note=f"http {status}")
    if status == 0:
      return ProbeResult("unknown", note=info.get("error", "network error"))
    return ProbeResult("unknown", note=f"http {status}")

  async def download(self, engine, url: str, dest_dir: str) -> DownloadResult:
    probe = await self.probe(engine, url)
    if probe.status == "dead":
      return DownloadResult("dead", note=probe.note)

    name = sanitize_filename(probe.filename or self._filename(url))
    dest = os.path.join(dest_dir, name)
    if os.path.exists(dest):
      return DownloadResult("skipped", path=dest, size=os.path.getsize(dest),
                            note="已存在")
    try:
      path = await engine.blob_download(url, dest_dir, filename=name)
    except Exception as e:
      return DownloadResult("failed", note=str(e))
    return DownloadResult("downloaded", path=path, size=os.path.getsize(path))
