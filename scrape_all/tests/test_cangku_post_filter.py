
from scrape_all.sites.cangku.post_filter import (
  DlItem, is_target_post, meta_labels, parse_collection_boxes, parse_info,
)

# 219673 帖子页顶部 meta 实拍结构（用户提供的 DOM 裁剪）
TARGET_META = """<div class="meta">
  <a href="/user/309550" class="">忍叶忍</a>
  <a href="/category/2" class="meta-label">动画</a>
  <a href="/category/32" class="meta-label">同人动画</a>
  <a href="/category/34" class="meta-label">其他动画</a>
  <time datetime="2026-08-13T13:48:00.000Z" title="2026-08-13 21:48:00">3 天前</time>
  <span>122778次围观</span>
  <a href="javascript:;" class="meta-label primary text-small"> 收藏  390 </a>
</div>"""


def page(body):
  return f"<html><body>{body}</body></html>"


def test_meta_labels_picks_category_chain_only():
  # 精确 class 匹配：作者链接/时间/围观数不带 class，收藏带附加 class，都不算分类
  assert meta_labels(page(TARGET_META)) == ["动画", "同人动画", "其他动画"]


def test_target_post_full_chain():
  assert is_target_post(page(TARGET_META)) is True


def test_non_target_post():
  manga = TARGET_META.replace("动画", "漫画")
  assert meta_labels(page(manga)) == ["漫画", "同人漫画", "其他漫画"]
  assert is_target_post(page(manga)) is False


def test_subcategory_alone_hits():
  # 只挂子分类（如 同人动画）也算工况内：判定是包含「动画」二字
  body = '<a href="/category/32" class="meta-label">同人动画</a>'
  assert is_target_post(page(body)) is True


def test_no_meta_labels():
  assert meta_labels(page("<div>没有分类</div>")) == []
  assert is_target_post(page("<div>没有分类</div>")) is False
  assert meta_labels("") == []


# ---- 合集 box 解析（fixture 来自 219673 「合集预定区」实拍 DOM 裁剪）----

COLLECTION_CARD = """<div class="collapse-card"><strong>
  <div class="collapse-header" id="heading-loxq_d">
    <div class="collapse-btn collapsed" data-toggle="collapse" data-target="#collapse-loxq_d" data-show="false" aria-expanded="false" aria-controls="collapse-loxq_d">合集预定区</div>
  </div></strong>
  <div id="collapse-loxq_d" class="collapse" aria-labelledby="heading-loxq_d"><div class="collapse-body"><div class="dl-box">
    <div class="title text-truncate">ZHAO</div>
    <div class="dl-body">
      <div class="dl-meta">
        <div class="meta"><span class="date">-</span></div>
        <div class="meta"><span class="from">自整理</span></div>
        <div class="meta"><span class="info">提取：yezi / 密码：yejiang</span></div>
      </div>
      <div class="dl-link">
        <div class="meta">下载链接</div>
        <a class="dl-item  qr-image-link" data-dlid="dlr_1" data-platform="default" href="javascript:void(0)"><i class="icon" style="background-image: url('https://api.cangku.moe/favicon?url=https%3A%2F%2Fcdnimg.hxcy.top%2Fuploads%2F2026%2F07%2F01SxI878ee48fc8786935.webp'), url('data:image/png;base64,iVBORw0KGgo=')"></i>百度网盘</a>
      </div>
    </div>
  </div></div></div>
</div>"""

OTHER_CARD = """<div class="collapse-card">
  <div class="collapse-header"><div class="collapse-btn">单集讨论</div></div>
  <div class="collapse"><div class="collapse-body"><div class="dl-box">
    <div class="title text-truncate">不该被抓</div>
    <div class="dl-body"><div class="dl-meta">
      <div class="meta"><span class="info">提取：skip / 密码：skip</span></div>
    </div></div>
  </div></div></div>
</div>"""


def test_parse_collection_boxes_full_fields():
  boxes = parse_collection_boxes(page(COLLECTION_CARD + OTHER_CARD))
  assert len(boxes) == 1                          # 只有标题带「合集」的卡
  b = boxes[0]
  assert b.card_title == "合集预定区"
  assert b.title == "ZHAO" and b.date == "-" and b.source == "自整理"
  assert b.info == "提取：yezi / 密码：yejiang"
  assert b.extract_pwd == "yezi" and b.unzip_pwd == "yejiang"
  assert b.items == [DlItem(
      name="百度网盘",
      qr_image_url="https://cdnimg.hxcy.top/uploads/2026/07/01SxI878ee48fc8786935.webp")]


def test_parse_collection_boxes_card_without_keyword():
  assert parse_collection_boxes(page(OTHER_CARD)) == []
  assert parse_collection_boxes("") == []


def test_item_without_qr_style_kept_with_empty_url():
  body = """<div class="collapse-card">
    <div class="collapse-btn">合集</div>
    <div class="dl-box"><div class="dl-body">
      <div class="dl-link"><div class="meta">下载链接</div>
        <a class="dl-item" href="javascript:void(0)">磁力</a>
      </div>
    </div></div>
  </div>"""
  boxes = parse_collection_boxes(page(body))
  assert len(boxes) == 1 and boxes[0].items == [DlItem(name="磁力", qr_image_url="")]


def test_qr_url_fragment_stripped():
  body = """<div class="collapse-card">
    <div class="collapse-btn">合集</div>
    <div class="dl-box"><div class="dl-body"><div class="dl-link">
      <a class="dl-item qr-image-link"><i class="icon" style="background-image: url('https://api.cangku.moe/favicon?url=https%3A%2F%2Fimage.acg.lol%2Ffile%2Fa.png#')"></i>百度网盘</a>
    </div></div></div>
  </div>"""
  boxes = parse_collection_boxes(page(body))
  assert boxes[0].items[0].qr_image_url == "https://image.acg.lol/file/a.png"


def test_parse_info_variants():
  assert parse_info("提取：yezi / 密码：yejiang") == ("yezi", "yejiang")
  assert parse_info("提取码：ab12，解压密码：cd34") == ("ab12", "cd34")
  assert parse_info("密码：xy") == ("", "xy")
  assert parse_info("") == ("", "")
  assert parse_info("提取：xxx") == ("xxx", "")
