
from scrape_all.sites.cangku.post_filter import (
  DlBox, FilterRules, PanLink, RawPost, classify_link, extract_pwd,
  filter_post, parse_onclick_args,
)

ONCLICK = "openDl('百度网盘', 'ab12', 'https://pan.baidu.com/s/1AbCdEf?pwd=xy99')"


def test_parse_onclick_args():
  assert parse_onclick_args(ONCLICK) == (
    "百度网盘", "ab12", "https://pan.baidu.com/s/1AbCdEf?pwd=xy99")
  assert parse_onclick_args("f(  )") == ()
  assert parse_onclick_args("no parens here") == ()
  assert parse_onclick_args("") == ()
  assert parse_onclick_args(None) == ()
  # 多余空格、双引号参数不识别（页面用的是单引号）
  assert parse_onclick_args("f( 'a' ,  'b' )") == ("a", "b")


def test_classify_link():
  assert classify_link("https://pan.baidu.com/s/1AbCdEf?pwd=xy99") == "baidu"
  assert classify_link("https://pan.baidu.com/share/init?surl=2UvUofV1") == "baidu"
  assert classify_link("https://pan.quark.cn/s/abc123") == "quark"
  assert classify_link("https://www.aliyundrive.com/s/xyz") == "aliyun"
  assert classify_link("https://www.alipan.com/s/xyz") == "aliyun"
  assert classify_link("magnet:?xt=urn:btih:abc") == "magnet"
  assert classify_link("https://example.com/file") == "other"


def test_extract_pwd_sources_in_priority_order():
  assert extract_pwd("https://pan.baidu.com/s/1x?pwd=xy99") == "xy99"       # url 查询参数
  assert extract_pwd("https://pan.baidu.com/s/1x", "百度网盘 提取码:ab12") == "ab12"
  assert extract_pwd("https://pan.baidu.com/s/1x", "百度网盘 提取码：cd34") == "cd34"
  assert extract_pwd("https://pan.baidu.com/s/1x", "夸克", ("ef56",)) == "ef56"   # 独立 4 位参数
  assert extract_pwd("https://pan.baidu.com/s/1x") is None
  # url 优先于其他来源
  assert extract_pwd("https://pan.baidu.com/s/1x?pwd=xy99", "提取码:ab12", ("ef56",)) == "xy99"


def box(card_title="合集", links=None, meta=None):
  return DlBox(card_title=card_title, meta=meta or {}, links=links or {})


def test_filter_post_label_gate():
  raw = RawPost(labels=["漫画"], boxes=[box()])
  assert filter_post(raw) is None
  raw = RawPost(labels=["动画", "2025年10月"], boxes=[box()])
  assert filter_post(raw) is not None
  # 标签带空白可命中
  raw = RawPost(labels=["  动画  "], boxes=[box()])
  assert filter_post(raw) is not None


def test_filter_post_collection_keyword():
  raw = RawPost(labels=["动画"], boxes=[
    box(card_title="合集", links={"百度网盘": ONCLICK}),
    box(card_title="单集", links={"百度网盘": ONCLICK}),
  ])
  content = filter_post(raw)
  assert len(content.links) == 1 and content.links[0].name == "百度网盘"

  # 关掉卡片限制则都保留
  content = filter_post(raw, FilterRules(collection_keyword=None))
  assert len(content.links) == 2


def test_filter_post_links_parsed():
  raw = RawPost(labels=["动画"], boxes=[box(links={
    "百度网盘": ONCLICK,
    "磁力": "openDl('磁力', '', 'magnet:?xt=urn:btih:abc')",
    "坏链接": "not-an-onclick",
  })])
  content = filter_post(raw)
  assert content.links == [
    PanLink(name="百度网盘", url="https://pan.baidu.com/s/1AbCdEf?pwd=xy99",
            pwd="xy99", pan_type="baidu"),
    PanLink(name="磁力", url="magnet:?xt=urn:btih:abc", pwd=None, pan_type="magnet"),
  ]
  # onclick 没解出参数的（第三参为空串）会进 skipped
  raw_empty = RawPost(labels=["动画"], boxes=[box(links={"坏链接": "openDl('x', 'y', '')"})])
  content = filter_post(raw_empty)
  assert content.links == [] and len(content.skipped) == 1


def test_filter_post_no_boxes_returns_empty_content():
  raw = RawPost(labels=["动画"], boxes=[])
  content = filter_post(raw)
  assert content is not None and content.links == []
