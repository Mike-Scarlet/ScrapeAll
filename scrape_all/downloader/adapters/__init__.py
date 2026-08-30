
from scrape_all.downloader.adapters.base import (
    DownloadResult, HostAdapter, ProbeResult, host_of,
)
from scrape_all.downloader.adapters.catbox import CatboxAdapter
from scrape_all.downloader.adapters.eros_uploads import ErosUploadsAdapter
from scrape_all.downloader.adapters.gofile import GofileAdapter
from scrape_all.downloader.adapters.hanime import HanimeAdapter
from scrape_all.downloader.adapters.mega import MegaAdapter
from scrape_all.downloader.adapters.pixeldrain import PixeldrainAdapter
from scrape_all.downloader.adapters.rule34 import Rule34Adapter

# adapter 注册表：接入新家就在这里加一行。逐家接入（catbox 先跑通契约，
# 站内 uploads 次之，pixeldrain / gofile / mega 已接，hanime / rule34 是
# 流媒体源站前两家，后续 gdrive / workupload）。
_ADAPTERS = [
    CatboxAdapter(),
    ErosUploadsAdapter(),
    PixeldrainAdapter(),
    GofileAdapter(),
    MegaAdapter(),
    HanimeAdapter(),
    Rule34Adapter(),
]


def adapter_for(url: str) -> HostAdapter | None:
  """URL -> 负责它的 adapter；没有返回 None（编排层按无 adapter 处理）"""
  for adapter in _ADAPTERS:
    if adapter.matches(url):
      return adapter
  return None


def all_hosts() -> frozenset:
  """注册表当前覆盖的全部 host（EroLink 登记时判有无 adapter 用）"""
  hosts: set = set()
  for adapter in _ADAPTERS:
    hosts |= adapter.hosts
  return frozenset(hosts)
