
import os
import re
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from scrape_all.sites.eroscripts.consts import ErosDef

# topic 页链接解析（纯离线，读 fetch 阶段落盘的 topic JSON）。
#
# 应对「各帖非标准化」的策略：不假设帖子结构，沿 DOM 顺序收全部 <a> 链接并
# 记录上下文（所在小节标题 / 楼层 / 作者），分类只依赖链接自身特征，优先级：
#   1) 附件标记（class=attachment 或站内 /uploads/ 路径）——本站惯例脚本以
#      .funscript 附件直接挂帖，锚文本就是文件名；
#   2) 文件扩展名（.funscript/.lua -> script；视频扩展名 -> media）；
#   3) 域名表（网盘 -> media；流媒体源页 -> source；其余 other）。
# links_json 全量落库（含 other），规则升级后离线重跑 parse 即可重新分类，不用重抓。
#
# 站内模板帖的 emoji 小节标题（🎬 Video Link / 📂 Script / 🖼 Preview）用
# heading 锚记：链接记录里带 section 字段，非模板帖该字段为空但链接照收。
# <code>/<pre> 里 discourse 不自动转链接，补一轮裸 URL 正则。

SCRIPT_EXTS = {".funscript", ".lua"}   # 播放器脚本（多轴脚本就是 .funscript）
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".wmv", ".mov", ".webm", ".m4v"}

# 网盘/文件托管域名（剥 www. 后匹配）——媒体下载链接的主形态
MEDIA_HOSTS = frozenset({
    "mega.nz", "mega.is", "app.mega.nz", "mega.co.nz",
    "pixeldrain.com",
    "drive.google.com", "docs.google.com",
    "disk.yandex.com", "yadi.sk",
    "pan.baidu.com",
    "mediafire.com", "app.mediafire.com",
    "gofile.io", "dropbox.com", "www.dropbox.com",
    "1fichier.com", "workupload.com",
    "catbox.moe", "litterbox.catbox.moe",
    "send.cm", "anonfiles.com", "terabox.com",
})
# 流媒体/出处页（视频在哪能看到，但不是网盘下载）。
# 首轮全量 parse 后按 other 域名分布补过一轮：hanime1.me 是 hanime 镜像（108 条）、
# iwara.ai 是 iwara 备用域、hstream/hentaimama/freehentaistream 是里番流媒体站
SOURCE_HOSTS = frozenset({
    "iwara.tv", "iwara.ai", "rule34video.com",
    "hanime.tv", "hanime1.me", "hmvmania.com",
    "hstream.moe", "hentaimama.io", "freehentaistream.com",
    "eporner.com", "spankbang.com", "pornhub.com", "xvideos.com",
})

_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_BARE_URL_RE = re.compile(r"https?://[^\s<>\"'`]+")

_site_host = urlsplit(ErosDef.root_url).netloc   # discuss.eroscripts.com


@dataclass
class TopicLink:
  """单条链接及其上下文；links_json 里每项即 asdict(topic_link)"""
  kind: str        # script / media / source / other
  url: str         # 绝对化后的 URL（附件是站内 /uploads/ 绝对地址）
  name: str        # 锚文本（附件=文件名；图片链接等空文本回退域名/文件名）
  section: str     # 所在小节标题文本（模板帖的 emoji 标题，非模板帖为空）
  post_number: int # 所在楼层（1=OP）
  username: str    # 发链接的用户（脚本更新常出现在作者自己的回帖里）


def host_of(url: str) -> str:
  """剥 www. 的 netloc，域名表匹配用"""
  netloc = urlsplit(url).netloc.lower()
  return netloc[4:] if netloc.startswith("www.") else netloc


def _ext_of(url: str) -> str:
  return os.path.splitext(urlsplit(url).path)[1].lower()


def link_kind(url: str, is_attachment: bool, name: str = "") -> str:
  """链接分类：附件标记/扩展名/文件名特征 > 域名表；认不出给 other"""
  ext = _ext_of(url)
  if ext in SCRIPT_EXTS:
    return "script"
  if ext in VIDEO_EXTS:
    return "media"
  if is_attachment:   # 站点上传附件无视频扩展名：按脚本论（本站附件即脚本包）
    return "script"
  # 文件名/锚文本带 funscript 字样的打包直链（如流媒体站 CDN 挂的脚本 zip）
  base = os.path.basename(urlsplit(url).path).lower()
  if "funscript" in base or "funscript" in name.lower():
    return "script"
  host = host_of(url)
  if host in MEDIA_HOSTS:
    return "media"
  if host in SOURCE_HOSTS:
    return "source"
  return "other"


def _collapse(text: str) -> str:
  return " ".join(text.split())


def _clean_bare(u: str) -> str:
  return u.rstrip(".,;:!?)]}>'\"")


def extract_post_links(cooked: str, post_number: int,
                       username: str) -> list[TopicLink]:
  """单个 post 的 cooked HTML -> 链接列表（post 内 URL 去重，按 DOM 顺序）"""
  soup = BeautifulSoup(cooked or "", "html.parser")
  section = ""
  links: list[TopicLink] = []
  seen: set[str] = set()   # code 在 pre 里会出现两次，post 内先去一道

  def add(url: str, name: str, is_attachment: bool):
    if url in seen:
      return
    seen.add(url)
    links.append(TopicLink(
        kind=link_kind(url, is_attachment, name), url=url, name=_collapse(name),
        section=section, post_number=post_number, username=username or ""))

  for el in soup.find_all([*_HEADINGS, "a", "code", "pre"]):
    if el.name in _HEADINGS:
      section = _collapse(el.get_text(" ", strip=True))
      continue
    if el.name in ("code", "pre"):
      # code 块里不自动转链，补裸 URL（code 在 pre 里会出现两次，靠最终去重吸收）
      for u in _BARE_URL_RE.findall(el.get_text()):
        add(_clean_bare(u), "", False)
      continue

    cls = el.get("class") or []
    if "anchor" in cls or "lightbox" in cls:   # 页内锚点 / 图片预览，噪声
      continue
    href = el.get("href") or ""
    if not href or href.startswith("#"):
      continue
    url = urljoin(ErosDef.root_url + "/", href)
    if not url.startswith(("http://", "https://")):   # mailto: 等
      continue
    path = urlsplit(url).path
    is_attachment = ("attachment" in cls
                     or (host_of(url) == _site_host and path.startswith("/uploads/")))
    if not is_attachment and host_of(url) == _site_host:
      continue   # 站内其余链接是引用/导航，跳过
    name = el.get_text(" ", strip=True)
    if not name:   # 图片/图标链接没文本：路径像文件名（带扩展名）用文件名，否则用域名
      base = os.path.basename(path.rstrip("/"))
      name = base if "." in base else host_of(url)
    add(url, name, is_attachment)

  return links


def parse_topic_links(topic: dict) -> list[TopicLink]:
  """topic 页 JSON -> 全帖链接（按楼层升序，URL 精确去重取首现，OP 优先保住）"""
  posts = (topic.get("post_stream") or {}).get("posts") or []
  seen: set[str] = set()
  out: list[TopicLink] = []
  for post in sorted(posts, key=lambda p: p.get("post_number") or 0):
    if post.get("deleted_at"):
      continue
    for link in extract_post_links(post.get("cooked") or "",
                                   post.get("post_number") or 0,
                                   post.get("username") or ""):
      if link.url in seen:
        continue
      seen.add(link.url)
      out.append(link)
  return out


def links_to_json(links: list[TopicLink]) -> list[dict]:
  return [asdict(l) for l in links]
