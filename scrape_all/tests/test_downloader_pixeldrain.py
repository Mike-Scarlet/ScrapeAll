
from scrape_all.downloader.adapters import adapter_for
from scrape_all.downloader.adapters.catbox import CatboxAdapter
from scrape_all.downloader.adapters.eros_uploads import ErosUploadsAdapter
from scrape_all.downloader.adapters.pixeldrain import (
    PixeldrainAdapter, _SIZE_LABEL_RE, name_from_title, parse_pd_url,
    parse_size_text, pd_page_url,
)


class TestParsePdUrl:
  def test_u_form_is_file(self):
    assert parse_pd_url("https://pixeldrain.com/u/etStjhv5") == \
        ("file", "etStjhv5", "u")

  def test_d_form_is_file(self):
    assert parse_pd_url("https://pixeldrain.com/d/kV6Aqw71") == \
        ("file", "kV6Aqw71", "d")

  def test_l_form_is_list(self):
    assert parse_pd_url("https://pixeldrain.com/l/x2CLfTjy") == \
        ("list", "x2CLfTjy", "l")

  def test_bare_api_forms(self):
    assert parse_pd_url("https://pixeldrain.com/api/file/mE7i8QPx") == \
        ("file", "mE7i8QPx", "api_file")
    assert parse_pd_url("https://pixeldrain.com/api/list/abc123") == \
        ("list", "abc123", "api_list")
    assert parse_pd_url("http://pixeldrain.com/api/file/mE7i8QPx") == \
        ("file", "mE7i8QPx", "api_file")

  def test_query_string_ignored(self):
    assert parse_pd_url("https://pixeldrain.com/d/xyz?foo=bar") == \
        ("file", "xyz", "d")

  def test_unknown_forms(self):
    assert parse_pd_url("https://pixeldrain.com/") is None
    assert parse_pd_url("https://pixeldrain.com/user/login") is None
    assert parse_pd_url("https://pixeldrain.com/l/") is None


class TestPageUrlRouting:
  # 形态透传：/u 与 /d 页面逐文件互斥，帖子原始形态决定开哪个页

  def test_d_form_opens_d_page(self):
    assert pd_page_url("file", "E1Kk51Ls", "d") == \
        "https://pixeldrain.com/d/E1Kk51Ls"

  def test_u_and_api_file_forms_open_u_page(self):
    assert pd_page_url("file", "PV82t9fy", "u") == \
        "https://pixeldrain.com/u/PV82t9fy"
    assert pd_page_url("file", "mE7i8QPx", "api_file") == \
        "https://pixeldrain.com/u/mE7i8QPx"

  def test_lists_always_open_l_page(self):
    assert pd_page_url("list", "x2CLfTjy", "l") == \
        "https://pixeldrain.com/l/x2CLfTjy"
    assert pd_page_url("list", "abc123", "api_list") == \
        "https://pixeldrain.com/l/abc123"


class TestSizeLabel:
  def test_label_anchors_size_not_bandwidth(self):
    # /d 页：.stat 混着 "Transfer used" 带宽，只认 "Size" 标签后面的值
    m = _SIZE_LABEL_RE.search("Downloads\n975\nTransfer used\n185 GB\nSize\n129 MB")
    assert m and parse_size_text(m.group(1)) == 129 * 1000 * 1000

  def test_label_on_shared_u_page_block(self):
    # /u 页：三个 .stat 共享一个标签父块
    m = _SIZE_LABEL_RE.search("Views\n184\nDownloads\n142\nSize\n1.64 GB")
    assert m and parse_size_text(m.group(1)) == int(1.64 * 1000 ** 3)

  def test_no_label_no_match(self):
    assert _SIZE_LABEL_RE.search("Downloads\n975") is None
    assert _SIZE_LABEL_RE.search("") is None


class TestTitleAndSize:
  def test_name_from_title(self):
    assert name_from_title(
        "(Hare) Hololive EN - Gawr Gura.mp4 ~ pixeldrain") == \
        "(Hare) Hololive EN - Gawr Gura.mp4"
    assert name_from_title("404, File Not Found ~ pixeldrain") == \
        "404, File Not Found"

  def test_name_from_title_without_suffix(self):
    # 站点后缀不在时原样返回
    assert name_from_title("plain name") == "plain name"

  def test_parse_size_text(self):
    # pixeldrain 页面是 SI 单位（实测 14.0 MB = 14020206 字节）
    assert parse_size_text("14.0 MB") == 14 * 1000 * 1000
    assert parse_size_text("1.5 GB") == int(1.5 * 1000 ** 3)
    assert parse_size_text("512 KB") == 512 * 1000
    assert parse_size_text("128 B") == 128

  def test_parse_size_text_negative(self):
    assert parse_size_text("2,481 views") is None
    assert parse_size_text("") is None
    assert parse_size_text(None) is None


class TestRegistry:
  def test_pixeldrain_routing(self):
    a = adapter_for("https://pixeldrain.com/l/x2CLfTjy")
    assert isinstance(a, PixeldrainAdapter)
    assert isinstance(adapter_for("https://pixeldrain.com/u/abc"), PixeldrainAdapter)

  def test_catbox_routing(self):
    assert isinstance(adapter_for("https://files.catbox.moe/1z4mvb.mp4"),
                      CatboxAdapter)

  def test_eros_uploads_only_uploads_path(self):
    assert isinstance(
        adapter_for("https://discuss.eroscripts.com/uploads/short-url/x.funscript"),
        ErosUploadsAdapter)
    # 站内 topic 页等不是附件，不归这个 adapter
    assert adapter_for("https://discuss.eroscripts.com/t/some-topic/123") is None

  def test_unknown_host(self):
    assert adapter_for("https://example.com/file.zip") is None
