
import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

# 纯逻辑模块：页面层只取原始数据（文本/属性），筛选与解析判断全在这里

# onclick="openDl('名称', '提取码', 'url')" -> 取括号里的单引号字符串参数
ONCLICK_ARGS_RE = re.compile(r"\(([^)]*)\)")
QUOTED_RE = re.compile(r"'([^']*)'")


def parse_onclick_args(onclick: Optional[str]) -> tuple[str, ...]:
  """onclick 属性原文 -> 字符串参数组；解不出返回空组"""
  if not onclick:
    return ()
  m = ONCLICK_ARGS_RE.search(onclick)
  if not m:
    return ()
  return tuple(QUOTED_RE.findall(m.group(1)))


@dataclass
class DlBox:
  """一个 dl-box 的原始数据（页面层取数，未筛选）"""
  card_title: str = ""                        # 所在折叠卡按钮文本（"合集"判断用）
  meta: dict = field(default_factory=dict)    # meta 项 class 名 -> 文本
  links: dict = field(default_factory=dict)   # dl-item 显示名 -> onclick 属性原文


@dataclass
class RawPost:
  """帖子页解析出的原始内容"""
  labels: list = field(default_factory=list)
  boxes: list = field(default_factory=list)


@dataclass
class PanLink:
  """筛选后保留的一条网盘链接"""
  name: str              # dl-item 显示名
  url: str
  pwd: Optional[str] = None
  pan_type: str = ""     # baidu / quark / aliyun / magnet / other


BAIDU_RE = re.compile(r"pan\.baidu\.com", re.I)
QUARK_RE = re.compile(r"pan\.quark\.cn", re.I)
ALIYUN_RE = re.compile(r"(aliyundrive|alipan)", re.I)


def classify_link(url: str) -> str:
  if url.startswith("magnet:"):
    return "magnet"
  if BAIDU_RE.search(url):
    return "baidu"
  if QUARK_RE.search(url):
    return "quark"
  if ALIYUN_RE.search(url):
    return "aliyun"
  return "other"


# 提取码按可信度依次找：url 查询参数 > 文本"提取码xxxx" > onclick 里独立的 4 位参数
PWD_QUERY_RE = re.compile(r"[?&](?:pwd|password|code)=([A-Za-z0-9]{4})", re.I)
PWD_TEXT_RE = re.compile(r"提取码[:：\s]*([A-Za-z0-9]{4})")
PWD_ARG_RE = re.compile(r"^[A-Za-z0-9]{4}$")


def extract_pwd(url: str, name: str = "", extra_args: Sequence[str] = ()) -> Optional[str]:
  m = PWD_QUERY_RE.search(url or "")
  if m:
    return m.group(1)
  m = PWD_TEXT_RE.search(name or "")
  if m:
    return m.group(1)
  for arg in extra_args:
    if PWD_ARG_RE.match(arg):
      return arg
  return None


@dataclass
class FilterRules:
  require_label: Optional[str] = "动画"        # 帖子标签必须包含；None = 不限
  collection_keyword: Optional[str] = "合集"   # 折叠卡标题必须包含；None = 不限


@dataclass
class PostContent:
  """筛选后的帖子内容"""
  links: list = field(default_factory=list)    # PanLink 列表（所有网盘类型，pan_type 区分）
  skipped: list = field(default_factory=list)  # 解析失败的链接描述，排查用


def filter_post(raw: RawPost, rules: Optional[FilterRules] = None) -> Optional[PostContent]:
  """按规则筛选帖子。返回 None = 不是目标帖；PostContent = 保留内容（links 可能为空）"""
  if rules is None:
    rules = FilterRules()

  labels = [label.strip() for label in raw.labels]
  if rules.require_label and rules.require_label not in labels:
    return None

  content = PostContent()
  for box in raw.boxes:
    if rules.collection_keyword and rules.collection_keyword not in box.card_title:
      continue
    for name, onclick in box.links.items():
      args = parse_onclick_args(onclick)
      url = args[-1] if args else ""
      if not url:
        content.skipped.append(f"{name}: onclick 无法解析 ({onclick})")
        continue
      pwd = extract_pwd(url, name, args[:-1])
      content.links.append(PanLink(name=name, url=url, pwd=pwd, pan_type=classify_link(url)))
  return content
