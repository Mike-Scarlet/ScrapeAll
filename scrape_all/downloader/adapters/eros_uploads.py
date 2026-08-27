
import json
import os
from urllib.parse import urlsplit

from scrape_all.downloader.adapters.base import (
    DownloadResult, HostAdapter, ProbeResult,
    filename_from_cd, size_from_range_headers, timeout_for_size,
)
from scrape_all.downloader.fsutil import sanitize_filename

# eroscripts 站内附件（discourse /uploads/，脚本主形态，2693 条）。
# 附件响应带 Content-Disposition: attachment —— goto 会变成下载事件
# （net::ERR_ABORTED），所以这家的正确姿势：
#   probe   park 在站点根页（普通导航能 commit），同源页内 fetch 附件 URL 探头
#   download direct_download：goto 直接触发浏览器下载器，suggested_filename
#           就是 content-disposition 里的原始文件名（短链 URL 名是 base62 串）
# 附件走站内登录态（browser_session/ 持久 profile，与 collect/fetch 同一份）。


class ErosUploadsAdapter(HostAdapter):
  hosts = frozenset({"discuss.eroscripts.com"})

  _root = "https://discuss.eroscripts.com/"

  @staticmethod
  def _url_name(url: str) -> str:
    return os.path.basename(urlsplit(url).path) or "attachment"

  @classmethod
  def matches(cls, url: str) -> bool:
    # 站内其余路径（topic 页等）不是附件，只认 /uploads/
    return super().matches(url) and urlsplit(url).path.startswith("/uploads/")

  async def probe(self, engine, url: str) -> ProbeResult:
    info = await engine.probe_headers(url, park_url=self._root)
    status = info.get("status", 0)
    headers = info.get("headers", {})
    if status in (200, 206):
      return ProbeResult(
          "alive",
          filename=filename_from_cd(headers) or self._url_name(url),
          size=size_from_range_headers(headers),
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

    name = sanitize_filename(probe.filename or self._url_name(url))
    dest = os.path.join(dest_dir, name)
    if os.path.exists(dest):
      return DownloadResult("skipped", path=dest, size=os.path.getsize(dest),
                            note="已存在")
    try:
      path = await engine.direct_download(url, dest_dir, filename=name,
                                          timeout_s=timeout_for_size(probe.size))
    except Exception as e:
      return DownloadResult("failed", note=str(e))
    size = os.path.getsize(path)
    # funscript 是 JSON：顺手校验内容形态，防把登录页 HTML 存成 .funscript
    if name.endswith(".funscript"):
      try:
        with open(path, encoding="utf-8") as f:
          payload = json.load(f)
        if not (isinstance(payload, dict) and "actions" in payload):
          return DownloadResult("failed", path=path, size=size,
                                note="内容不是 funscript 结构（无 actions）")
      except (ValueError, OSError) as e:
        return DownloadResult("failed", path=path, size=size,
                              note=f"内容不是合法 JSON: {e}")
    return DownloadResult("downloaded", path=path, size=size)
