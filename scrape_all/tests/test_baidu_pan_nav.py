
from scrape_all.sites.baidu_pan.pages.shared_link_page import (
  build_hash_url, current_hash_path, extract_share_prefix, parent_of,
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


def test_current_hash_path():
  assert current_hash_path("https://pan.baidu.com/s/1x?pwd=ab#list/path=%2F") == "/"
  assert current_hash_path("https://pan.baidu.com/s/1x?pwd=ab") is None
  assert current_hash_path(None) is None
  deep = ("https://pan.baidu.com/s/12UvUofV1eOoEA_bElixaDQ?pwd=yezi"
          "#list/path=%2Fsharelink1102155816383-539367556653365%2FMimu%2F2025"
          "&parentPath=%2Fsharelink1102155816383-539367556653365%2FMimu")
  assert current_hash_path(deep) == "/sharelink1102155816383-539367556653365/Mimu/2025"
  # hash 后带额外参数（如 &vmode=list）不影响解析
  extra = "https://pan.baidu.com/s/1x#list/path=%2F&vmode=list"
  assert current_hash_path(extra) == "/"
