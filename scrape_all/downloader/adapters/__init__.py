
from scrape_all.downloader.adapters.base import (
    DownloadResult, HostAdapter, ProbeResult, host_of,
)
from scrape_all.downloader.adapters.catbox import CatboxAdapter
from scrape_all.downloader.adapters.eros_uploads import ErosUploadsAdapter
from scrape_all.downloader.adapters.gofile import GofileAdapter
from scrape_all.downloader.adapters.pixeldrain import PixeldrainAdapter

# adapter 注册表：接入新家就在这里加一行。逐家接入（catbox 先跑通契约，
# 站内 uploads 次之，pixeldrain / gofile 已接，后续 mega / gdrive / workupload）。
_ADAPTERS = [
    CatboxAdapter(),
    ErosUploadsAdapter(),
    PixeldrainAdapter(),
    GofileAdapter(),
]


def adapter_for(url: str) -> HostAdapter | None:
  """URL -> 负责它的 adapter；没有返回 None（编排层按无 adapter 处理）"""
  for adapter in _ADAPTERS:
    if adapter.matches(url):
      return adapter
  return None
