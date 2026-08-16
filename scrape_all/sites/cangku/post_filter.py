
import re
from dataclasses import dataclass, field
from urllib.parse import unquote

from bs4 import BeautifulSoup

from scrape_all.sites.cangku import locators

# 纯逻辑模块：帖子页解析。
# 第一步 分类过滤（严格）：meta-label（分类链）出现「动画」二字才工况内，
#   否则 OUT_OF_SCOPE——包括一条分类都没挂的帖子。
# 个别想要的例外走 config.CANGKU_FORCE_IDS 后门（parse 阶段按 id 放行）。
# 第二步 合集 box 解析（第一种情况，qr-image-link）：折叠卡标题含「合集」的 dl-box——
#   dl-meta 的 info 里写 提取码/解压密码；dl-item 的 icon 样式里 favicon?url= 包着
#   二维码原图地址（url 解码后可直接下载），二维码内容即真实网盘链接（见 qr.py）。
# 折叠卡不用真的点开：Vue 只是视觉折叠，DOM 全量渲染（219673 验证）。
# box 内可能同时放多个平台的下载项（219421：百度网盘 + Pikpak）：只取名字带
#   「百度」二字的项，其余平台项跳过，不取图不记异常。
# 项地址也可能直接就是盘链（217547：pan.baidu.com/s/1xxx、share/init?surl=xxx）：
#   没有二维码可解，地址本身即链接。

TARGET_CATEGORY = "动画"
COLLECTION_KEYWORD = "合集"
BAIDU_ITEM_KEYWORD = "百度"   # 放宽匹配：百度网盘 / 百度网盘(二维码) 等写法都命中


def meta_labels(html: str) -> list[str]:
  """帖子页分类 meta-label 文本列表（精确 class 匹配，不含收藏/点赞等附加 class 项）"""
  soup = BeautifulSoup(html, "lxml")
  return [" ".join(el.get_text(" ", strip=True).split()) for el in soup.select(locators.META_LABEL)]


def is_target_post(html: str) -> bool:
  """严格工况内判定：任一分类 meta-label 文本包含「动画」。
  没挂标签 / 挂了别的分类都算工况外；例外帖子走 CANGKU_FORCE_IDS 后门"""
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


# ---- 合集 box -> 链接清单（parse 阶段用，decode 回调注入保持纯逻辑）----

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


def direct_pan_link(url: str) -> str:
  """项地址本身就是网盘链接（pan.baidu.com/s/1xxx、share/init?surl=xxx，
  217547 形态）时原样返回——不再解二维码，地址即链接；否则空串（走二维码）"""
  return url if classify_link(url) != "other" else ""


@dataclass
class PostLinks:
  links: list = field(default_factory=list)      # list[dict]，落 links_json
  anomalies: list = field(default_factory=list)  # 不符合当前规则的结构描述


def is_baidu_item(item: DlItem) -> bool:
  """下载项筛选：名字带「百度」二字即可（百度网盘 / 百度网盘(二维码) 等）"""
  return BAIDU_ITEM_KEYWORD in item.name


def baidu_qr_urls(boxes: list) -> list[str]:
  """合集 box 里需要取图解码的地址（parse 阶段浏览器取图清单）。
  项地址本身已是盘链的排除在外——没有二维码可取。"""
  return sorted({it.qr_image_url for b in boxes for it in b.items
                 if is_baidu_item(it) and it.qr_image_url
                 and not direct_pan_link(it.qr_image_url)})


def extract_links(boxes: list, decode) -> PostLinks:
  """合集 box 列表 -> (链接清单, 异常描述)。decode(二维码图地址) -> 盘链，
  解不出给空串（由调用方的浏览器取图 + cv2 解码实现）。
  box 内只取名字带「百度」的项，其他平台项（Pikpak 等）跳过；整个 box
  没有百度项才算异常。项地址本身已是盘链时直接采用、不调 decode（217547）。
  出现任何不符合当前规则的结构都记 anomaly 且整帖不产出链接
  （帖子保持待解析，等规则补全后重跑）。"""
  result = PostLinks()
  if not boxes:
    result.anomalies.append("工况内但没有任何「合集」折叠卡")
    return result
  for box in boxes:
    if not box.items:
      result.anomalies.append(f"box {box.title!r} 没有任何下载项")
      continue
    baidu_items = [it for it in box.items if is_baidu_item(it)]
    if not baidu_items:
      names = "/".join(it.name for it in box.items)
      result.anomalies.append(f"box {box.title!r} 没有「百度」下载项（只有 {names}）")
      continue
    for item in baidu_items:
      if not item.qr_image_url:
        result.anomalies.append(f"box {box.title!r} 项 {item.name!r} 无二维码地址")
        continue
      url = direct_pan_link(item.qr_image_url)
      if not url:
        url = decode(item.qr_image_url)
        if not url:
          result.anomalies.append(
              f"box {box.title!r} 项 {item.name!r} 二维码取图/解码失败 {item.qr_image_url}")
          continue
      pan_type = classify_link(url)
      if pan_type == "other":
        result.anomalies.append(
            f"box {box.title!r} 项 {item.name!r} 二维码内容非网盘链接: {url[:80]}")
        continue
      result.links.append({
          "name": item.name, "url": url,
          "pwd": box.extract_pwd, "unzip_pwd": box.unzip_pwd, "pan_type": pan_type,
          "box_title": box.title, "card_title": box.card_title,
          "source": box.source, "date": box.date,
      })
  return result
