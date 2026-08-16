
from scrape_all.sites.baidu_pan.pages.shared_link_page import (
  breadcrumb_matches, build_hash_url, extract_share_prefix, parent_of,
)


def test_build_hash_url_encodes_like_page():
  url = build_hash_url(
    "https://pan.baidu.com/s/abc?pwd=4bs4",
    "/sharelink1099915704074-927179428565472/[2025年10月] 魔法藥水",
    "/sharelink1099915704074-927179428565472",
  )
  assert url.startswith("https://pan.baidu.com/s/abc?pwd=4bs4#list/path=")
  # 分隔符 / 与中文/空格都要编码，与页面真实 URL 一致（P1 实测格式）
  assert "%2Fsharelink1099915704074-927179428565472%2F%5B2025%E5%B9%B410%E6%9C%88%5D%20" in url
  assert "&parentPath=%2Fsharelink1099915704074-927179428565472" in url


def test_build_hash_url_root():
  url = build_hash_url("https://pan.baidu.com/s/abc", "/", "/")
  assert url == "https://pan.baidu.com/s/abc#list/path=%2F&parentPath=%2F"


def test_extract_share_prefix():
  assert extract_share_prefix(
    "https://pan.baidu.com/s/1k?pwd=jd8v#list/path=%2Fsharelink1099915704074-1008195905640011%2Fx"
  ) == "/sharelink1099915704074-1008195905640011"
  assert extract_share_prefix("https://pan.baidu.com/s/1k?pwd=jd8v#list/path=%2F") is None
  assert extract_share_prefix(None) is None


def test_parent_of():
  assert parent_of("/Season 1") == "/"
  assert parent_of("/A/B/C") == "/A/B"
  assert parent_of("/") == "/"
  assert parent_of("") == "/"
  assert parent_of("/A/B/") == "/A"


def test_breadcrumb_matches():
  # 完整显示时精确比较
  assert breadcrumb_matches("/", "/")
  assert breadcrumb_matches("/[2025年10月] 魔法藥水救救我", "/[2025年10月] 魔法藥水救救我")
  assert not breadcrumb_matches("/A", "/B")
  # 根目录 "/" 不能前缀匹配任意目标（否则跳转前就会误判已到达）
  assert not breadcrumb_matches("/", "/A/B")

  # 长名字被面包屑截断（DOM 文本带真实的 "..."），退化为前缀比较
  truncated = "/[2025年10月] ONE PUNCH MAN S3（一拳..."
  target = "/[2025年10月] ONE PUNCH MAN S3（一拳超人S3）"
  assert breadcrumb_matches(truncated, target)
  assert not breadcrumb_matches(truncated, "/[2025年10月] SPY×FAMILY S3（間諜过家家S3）")
