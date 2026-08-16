
import re
from dataclasses import dataclass, field
from urllib.parse import unquote

from bs4 import BeautifulSoup

from scrape_all.sites.cangku import locators

# 纯逻辑模块：帖子页解析。
# 第一步 分类过滤：meta-label（分类链）出现「动画」二字才工况内，其余 OUT_OF_SCOPE。
# 第二步 合集 box 解析（第一种情况，qr-image-link）：折叠卡标题含「合集」的 dl-box——
#   dl-meta 的 info 里写 提取码/解压密码；dl-item 的 icon 样式里 favicon?url= 包着
#   二维码原图地址（url 解码后可直接下载），二维码内容即真实网盘链接（见 qr.py）。
# 折叠卡不用真的点开：Vue 只是视觉折叠，DOM 全量渲染（219673 验证）。

TARGET_CATEGORY = "动画"
COLLECTION_KEYWORD = "合集"


def meta_labels(html: str) -> list[str]:
  """帖子页分类 meta-label 文本列表（精确 class 匹配，不含收藏/点赞等附加 class 项）"""
  soup = BeautifulSoup(html, "lxml")
  return [" ".join(el.get_text(" ", strip=True).split()) for el in soup.select(locators.META_LABEL)]


def is_target_post(html: str) -> bool:
  """工况内判定：任一分类 meta-label 文本包含「动画」"""
  return any(TARGET_CATEGORY in label for label in meta_labels(html))


# ---- 合集 box 解析 ----

# info 原文形如「提取：yezi / 密码：yejiang」，密码项也可能写作 解压密码
EXTRACT_PWD_RE = re.compile(r"提取(?:码)?\s*[:：]\s*([A-Za-z0-9]+)")
UNZIP_PWD_RE = re.compile(r"(?:解压)?密码\s*[:：]\s*([A-Za-z0-9]+)")

# dl-item 图标样式：favicon 代理的 url 参数是 url 编码的二维码原图地址；# 后是 fragment
FAVICON_QR_RE = re.compile(r"favicon\?url=([^)'\"]+)")


@dataclass
class DlItem:
  name: str               # 显示名（如 百度网盘）
  qr_image_url: str = ""  # 二维码原图地址；非二维码类 dl-item（其他情况）为空


@dataclass
class DlBox:
  card_title: str = ""    # 所在折叠卡标题（「合集」筛选依据）
  title: str = ""         # dl-box 标题
  date: str = ""
  source: str = ""        # from 项（自整理 等）
  info: str = ""          # info 原文（提取码/解压密码写在里面）
  extract_pwd: str = ""   # 提取码
  unzip_pwd: str = ""     # 解压密码
  items: list = field(default_factory=list)   # list[DlItem]


def parse_info(info: str) -> tuple[str, str]:
  """info 原文 -> (提取码, 解压密码)；解不出的项为空串"""
  m = EXTRACT_PWD_RE.search(info or "")
  extract = m.group(1) if m else ""
  m = UNZIP_PWD_RE.search(info or "")
  unzip = m.group(1) if m else ""
  return extract, unzip


def item_qr_url(a_el) -> str:
  """dl-item 元素 -> 二维码原图地址（url 解码、去 fragment）；没有则空串"""
  icon = a_el.find("i", class_="icon")
  style = icon.get("style") if icon else None
  if not style:
    return ""
  m = FAVICON_QR_RE.search(style)
  if not m:
    return ""
  return unquote(m.group(1).split("#", 1)[0])


def parse_collection_boxes(html: str) -> list[DlBox]:
  """折叠卡标题含「合集」的全部 dl-box 结构化"""
  soup = BeautifulSoup(html, "lxml")
  boxes = []
  for card in soup.select(locators.COLLAPSE_CARD):
    btn = card.select_one(locators.COLLAPSE_BTN)
    card_title = btn.get_text(strip=True) if btn else ""
    if COLLECTION_KEYWORD not in card_title:
      continue
    for box_el in card.select(locators.DL_BOX):
      box = DlBox(card_title=card_title)
      title_el = box_el.select_one(".title")
      box.title = title_el.get_text(strip=True) if title_el else ""
      for meta_el in box_el.select(locators.DL_META_ITEM):
        span = meta_el.find("span")
        key = span.get("class")[0] if (span is not None and span.get("class")) else ""
        if key == "date":
          box.date = meta_el.get_text(strip=True)
        elif key == "from":
          box.source = meta_el.get_text(strip=True)
        elif key == "info":
          box.info = meta_el.get_text(strip=True)
      box.extract_pwd, box.unzip_pwd = parse_info(box.info)
      for a_el in box_el.select(locators.DL_ITEM):
        box.items.append(DlItem(name=a_el.get_text(strip=True), qr_image_url=item_qr_url(a_el)))
      boxes.append(box)
  return boxes
