
from scrape_all.sites.cangku.post_filter import (
  DlBox, DlItem, baidu_qr_urls, classify_link, extract_links, is_baidu_item,
  is_target_post, meta_labels, parse_collection_boxes, parse_info,
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
  # 严格入口：没挂分类也算工况外；例外帖走 CANGKU_FORCE_IDS 后门（parse 阶段按 id 放行）
  assert meta_labels(page("<div>没有分类</div>")) == []
  assert is_target_post(page("<div>没有分类</div>")) is False
  assert meta_labels("") == []
  assert is_target_post("") is False


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


# ---- extract_links：decode 回调注入，纯逻辑 ----

def box_of(title="ZHAO", extract="yezi", unzip="yejiang", items=None):
  return DlBox(card_title="合集预定区", title=title, date="-", source="自整理",
               info="x", extract_pwd=extract, unzip_pwd=unzip, items=items or [])


def test_extract_links_all_good():
  boxes = [box_of(items=[DlItem(name="百度网盘", qr_image_url="qr1")])]
  decode = {"qr1": "https://pan.baidu.com/s/1abc"}.get
  r = extract_links(boxes, decode)
  assert r.anomalies == []
  assert r.links == [{
      "name": "百度网盘", "url": "https://pan.baidu.com/s/1abc",
      "pwd": "yezi", "unzip_pwd": "yejiang", "pan_type": "baidu",
      "box_title": "ZHAO", "card_title": "合集预定区", "source": "自整理", "date": "-"}]


def test_extract_links_anomaly_paths():
  # 没有任何合集卡
  r = extract_links([], lambda u: "")
  assert r.links == [] and len(r.anomalies) == 1
  # box 无下载项 / 百度项无二维码 / 解码失败 / 内容非网盘 —— 各记一条，整帖不产出
  boxes = [
      box_of(title="空盒", items=[]),
      box_of(title="B", items=[
          DlItem(name="百度网盘", qr_image_url=""),
          DlItem(name="百度网盘", qr_image_url="qr-bad"),
          DlItem(name="百度网盘", qr_image_url="qr-other"),
      ]),
  ]
  decode = {"qr-bad": "", "qr-other": "https://example.com/x"}.get
  r = extract_links(boxes, decode)
  assert r.links == [] and len(r.anomalies) == 4


def test_extract_links_only_baidu_items():
  # 219421 形态：同盒 百度网盘(二维码图) + Pikpak(直链)——只产出百度项，
  # Pikpak 项不取图不记异常（decode 表里没有它的地址也不影响）
  boxes = [box_of(title="見ず水煮", items=[
      DlItem(name="百度网盘", qr_image_url="zhu.webp"),
      DlItem(name="Pikpak", qr_image_url="https://mypikpak.com/s/xxx"),
  ])]
  decode = {"zhu.webp": "https://pan.baidu.com/s/1abc"}.get
  r = extract_links(boxes, decode)
  assert r.anomalies == []
  assert [l["name"] for l in r.links] == ["百度网盘"]
  assert r.links[0]["box_title"] == "見ず水煮"


def test_extract_links_direct_pan_link():
  # 217547 形态：百度项地址本身即盘链，不解二维码直接采用；decode 不应被调到
  boxes = [box_of(title="セネト", items=[
      DlItem(name="百度网盘", qr_image_url="https://pan.baidu.com/s/1BrupIT7"),
      DlItem(name="百度网盘(二维码)", qr_image_url="https://pan.baidu.com/share/init?surl=cpjR"),
  ])]
  def boom(u):
    raise AssertionError("直链不应走解码")
  r = extract_links(boxes, boom)
  assert r.anomalies == []
  assert [l["url"] for l in r.links] == [
      "https://pan.baidu.com/s/1BrupIT7", "https://pan.baidu.com/share/init?surl=cpjR"]
  assert all(l["pan_type"] == "baidu" for l in r.links)


def test_extract_links_box_without_baidu_item():
  # 整盒只有其他平台项 -> 记异常保持待解析（不是静默丢掉）
  boxes = [box_of(title="topu", items=[DlItem(name="Pikpak", qr_image_url="p")])]
  r = extract_links(boxes, lambda u: "https://pan.baidu.com/s/1x")
  assert r.links == [] and len(r.anomalies) == 1
  assert "Pikpak" in r.anomalies[0]


def test_extract_links_pan_type_from_qr_content():
  # pan_type 看二维码内容不看按钮名：百度项解出夸克链仍是 quark
  boxes = [box_of(items=[DlItem(name="百度网盘", qr_image_url="q")])]
  r = extract_links(boxes, {"q": "https://pan.quark.cn/s/x"}.get)
  assert [l["pan_type"] for l in r.links] == ["quark"]


def test_baidu_item_name_match():
  # 「百度」二字即可：百度网盘(二维码) 也命中；Pikpak/磁力 不命中
  assert is_baidu_item(DlItem(name="百度网盘"))
  assert is_baidu_item(DlItem(name="百度网盘(二维码)"))
  assert not is_baidu_item(DlItem(name="Pikpak"))
  assert not is_baidu_item(DlItem(name="磁力"))


def test_baidu_qr_urls_only_baidu_items():
  boxes = [box_of(items=[
      DlItem(name="百度网盘", qr_image_url="b1"),
      DlItem(name="Pikpak", qr_image_url="p1"),
      DlItem(name="百度网盘(二维码)", qr_image_url="b1"),        # 重复地址去重
      DlItem(name="百度网盘", qr_image_url=""),                  # 无地址不计
      DlItem(name="百度网盘", qr_image_url="https://pan.baidu.com/s/1x"),  # 直链不取图
  ])]
  assert baidu_qr_urls(boxes) == ["b1"]


def test_classify_link():
  assert classify_link("https://pan.baidu.com/s/1x") == "baidu"
  assert classify_link("https://pan.quark.cn/s/x") == "quark"
  assert classify_link("https://www.alipan.com/s/x") == "aliyun"
  assert classify_link("magnet:?xt=urn:btih:abc") == "magnet"
  assert classify_link("https://example.com/f") == "other"
