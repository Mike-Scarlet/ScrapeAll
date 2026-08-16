
from scrape_all.sites.cangku.list_parse import parse_post_cards

# 结构取自 probe 实测的卡片 XML（内容换成无害占位）
CARD_WITH_DATETIME = """
<div class="post col-md-3 col-sm-6"><div class="post-card simple-post-card">
  <section class="post-card-wrap">
    <a href="/archives/219673" title="标题A" target="">
      <div class="cover"></div>
      <div class="title text-truncate">标题A</div>
      <div class="status clearfix"><span class="item view">122565</span>
        <time datetime="2026-08-13T13:48:00.000Z" class="item date float-right">3 天前</time>
      </div>
    </a>
  </section>
</div></div>
"""

CARD_WITHOUT_TIME_ELEMENT = """
<div class="post"><div class="post-card simple-post-card">
  <section class="post-card-wrap">
    <a href="/archives/100001" title="标题B">
      <div class="title text-truncate">标题B</div>
      <div class="status clearfix"><span class="item view">99</span></div>
    </a>
  </section>
</div></div>
"""

CARD_TITLE_ONLY_IN_DIV = """
<div class="post"><div class="post-card simple-post-card">
  <section class="post-card-wrap">
    <a href="/archives/100002">
      <div class="title text-truncate">标题C</div>
      <time datetime="2026-05-01T17:58:36.000Z">4 个月前</time>
    </a>
  </section>
</div></div>
"""


def wrap(*cards):
  return '<div id="user-post">' + "\n".join(cards) + "</div>"


def test_parse_post_cards_full_info():
  refs = parse_post_cards(wrap(CARD_WITH_DATETIME))
  assert len(refs) == 1
  assert refs[0].url == "https://cangku.moe/archives/219673"
  assert refs[0].title == "标题A"
  assert refs[0].time_text == "2026-08-13T13:48:00.000Z"


def test_parse_post_cards_multiple_and_fallbacks():
  refs = parse_post_cards(wrap(CARD_WITH_DATETIME, CARD_WITHOUT_TIME_ELEMENT, CARD_TITLE_ONLY_IN_DIV))
  assert len(refs) == 3

  assert refs[0].time_text == "2026-08-13T13:48:00.000Z"     # datetime 属性优先
  assert refs[1].time_text is None                            # 无 time 元素且尾部无时间
  assert refs[1].title == "标题B"
  assert refs[2].url == "https://cangku.moe/archives/100002"  # 相对 href 拼全
  assert refs[2].title == "标题C"                              # title 属性缺失时取 .title 文本
  assert refs[2].time_text == "2026-05-01T17:58:36.000Z"


def test_parse_post_cards_empty_container():
  assert parse_post_cards('<div id="user-post"></div>') == []
  assert parse_post_cards("") == []
