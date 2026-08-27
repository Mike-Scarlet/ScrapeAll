
import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit


def host_of(url: str) -> str:
  """剥 www. 的 netloc，与 eroscripts.topic_parse.host_of 同规则"""
  netloc = urlsplit(url).netloc.lower()
  return netloc[4:] if netloc.startswith("www.") else netloc


_CR_TOTAL_RE = re.compile(r"bytes\s+\d+-\d+/(\d+)", re.I)


def size_from_range_headers(headers: dict) -> int | None:
  """Range:0-0 探活响应里的真实大小：content-range 总长优先；服务端不理
  Range 时 content-length 就是整文件长度"""
  m = _CR_TOTAL_RE.match(headers.get("content-range", ""))
  if m:
    return int(m.group(1))
  cl = headers.get("content-length", "")
  return int(cl) if cl.isdigit() else None


def filename_from_cd(headers: dict) -> str | None:
  """从 content-disposition 挖原始文件名（filename*=UTF-8'' 优先于 filename=）。
  短链/哈希路径的 URL 文件名不是原名，这个名字才是真名"""
  cd = headers.get("content-disposition", "")
  if not cd:
    return None
  m = re.search(r"filename\*=(?:UTF-8|utf-8)''([^;]+)", cd)
  if m:
    return unquote(m.group(1).strip("\" "))
  m = re.search(r'filename="([^"]+)"', cd)
  if m:
    return m.group(1)
  m = re.search(r"filename=([^;]+)", cd)
  if m:
    return m.group(1).strip("\" ")
  return None


# 下载等待超时按体积推算：200KB/s 兜底网速 + 启动余量，地板取调用方默认。
# 起因 2026-08-26：catbox 185.6MB 走 blob 路径（页内 fetch 拉完全文件才出
# 下载事件），120s 默认超时在并发抢代理带宽下直接掐死——超时罩着整个传输
# 过程的路径（catbox blob、mega 页内拉取+解密）必须按体积放。
DL_TIMEOUT_SPEED_BPS = 200 * 1024
DL_TIMEOUT_HEADROOM_S = 60.0


def timeout_for_size(size: int | None, base_s: float = 120.0) -> float:
  """已知体积的下载等待超时（秒）：max(地板, 体积/200KBps + 60s 余量)。
  未知体积返回地板。直链类路径（下载事件在开始时就来）放长了只是晚失败，
  无副作用，所以各 adapter 统一用。"""
  if not size or size <= 0:
    return base_s
  return max(base_s, size / DL_TIMEOUT_SPEED_BPS + DL_TIMEOUT_HEADROOM_S)


def dl_wait_ms(size: int | None, base_s: float) -> int:
  """expect_download 要的是毫秒"""
  return int(timeout_for_size(size, base_s) * 1000)


# 探活结果。status:
#   alive      链接有效，元信息尽量填全
#   dead       404/410 或平台明确报"文件不存在/已删除"
#   needs_auth 要登录（可转人工） / paywall  付费墙（跳过）
#   unknown    探不明（异常/挑战页），留给下载时再见真章
@dataclass
class ProbeResult:
  status: str
  filename: str | None = None
  size: int | None = None                  # 字节；文件夹 host 可为 None
  files: list[dict] = field(default_factory=list)   # 文件夹 host 的文件清单 [{name,size,url}]
  note: str = ""


# 单链接下载结果。status:
#   downloaded 落盘成功 / dead 死链 / failed 失败（可重试）
#   skipped    已存在（断点续跑幂等）或按规则跳过
@dataclass
class DownloadResult:
  status: str
  path: str | None = None
  size: int = 0
  note: str = ""


class HostAdapter:
  """一家文件托管一个 adapter。职责：URL 归一 + probe/download，动作全走
  DownloadEngine（浏览器页内取回），不自己发 http。探活和下载都做成单链接
  可信——批量编排是上层的事，这里不管队列不管 stat。"""

  hosts: frozenset = frozenset()

  @classmethod
  def matches(cls, url: str) -> bool:
    return host_of(url) in cls.hosts

  async def probe(self, engine, url: str) -> ProbeResult:
    raise NotImplementedError

  async def download(self, engine, url: str, dest_dir: str) -> DownloadResult:
    raise NotImplementedError
