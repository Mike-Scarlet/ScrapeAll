
from scrape_all.downloader.adapters import adapter_for, all_hosts
from scrape_all.downloader.adapters.rule34 import (
    Rule34Adapter, filename_from_href, is_wait_timeout, local_filename,
    parse_rule34_url, pick_best_row, row_resolution,
)


class TestParseRule34Url:
  def test_video_form_with_slug(self):
    assert parse_rule34_url(
        "https://rule34video.com/video/4306862/4k-a-night-with-hina-skintone-b/"
    ) == "4306862"

  def test_no_trailing_slash(self):
    assert parse_rule34_url(
        "https://rule34video.com/video/12/some-slug") == "12"

  def test_extra_query_params(self):
    assert parse_rule34_url(
        "https://rule34video.com/video/99/x/?t=1#frag") == "99"
    assert parse_rule34_url("http://rule34video.com/video/1/") == "1"

  def test_non_video_forms(self):
    # 搜索 / 分类 / 根都不是视频页，probe/download 都不该碰
    assert parse_rule34_url("https://rule34video.com/search/hina/") is None
    assert parse_rule34_url("https://rule34video.com/categories/") is None
    assert parse_rule34_url("https://rule34video.com/") is None

  def test_non_numeric_id(self):
    assert parse_rule34_url("https://rule34video.com/video/abc/x/") is None


class TestRowResolution:
  def test_labels(self):
    assert row_resolution("MP4 2160p") == 2160
    assert row_resolution("MP4 1080p") == 1080
    assert row_resolution("mp4 480p") == 480

  def test_360p_label_has_p(self):
    # 360p 档 url 路径是 _360.mp4，锚文本仍带 p
    assert row_resolution("MP4 360p") == 360

  def test_unparseable(self):
    assert row_resolution("MP4") == -1
    assert row_resolution("") == -1
    assert row_resolution(None) == -1


class TestPickBestRow:
  def _rows(self, *texts):
    return [{"i": i, "text": t, "href": f"https://x/{i}"}
            for i, t in enumerate(texts)]

  def test_highest_within_cap_wins(self):
    # 2160p 在 1080p 上限之外，上限内最高的是 1080p
    rows = self._rows("MP4 2160p", "MP4 1080p", "MP4 720p")
    assert pick_best_row(rows) is rows[1]

  def test_unordered_rows(self):
    # 乱序也取上限内最高的（720p，2160p 被上限排除）
    rows = self._rows("MP4 480p", "MP4 2160p", "MP4 720p")
    assert pick_best_row(rows) is rows[2]

  def test_cap_excludes_tiers_above_1080(self):
    # 上限 1080p：更高档（含 2160p）不选，退而取 1080p
    rows = self._rows("MP4 4320p", "MP4 2160p", "MP4 1080p")
    assert pick_best_row(rows) is rows[2]

  def test_all_above_cap_falls_back_to_first_row(self):
    # 上限是选档偏好不是硬墙：全超上限时保页面原序兜底（note 里可见）
    rows = self._rows("MP4 4320p", "MP4 2880p")
    assert pick_best_row(rows) is rows[0]

  def test_unparseable_falls_back_to_page_order(self):
    rows = self._rows("高清", "标清")
    assert pick_best_row(rows) is rows[0]

  def test_parseable_beats_unparseable(self):
    rows = self._rows("特殊档", "MP4 480p")
    assert pick_best_row(rows) is rows[1]

  def test_same_resolution_keeps_page_order(self):
    rows = self._rows("MP4 1080p", "MP4 1080p")
    assert pick_best_row(rows) is rows[0]

  def test_empty(self):
    assert pick_best_row([]) is None


class TestFilenameFromHref:
  def test_download_filename_param_wins(self):
    href = ("https://rule34video.com/get_file/54/abc/4306000/4306862/"
            "4306862_2160p.mp4/?v-acctoken=tok&download=true"
            "&download_filename=4k-a-night-with-hina-skintone-b_2160p.mp4")
    assert filename_from_href(href) == "4k-a-night-with-hina-skintone-b_2160p.mp4"

  def test_url_encoded_filename_param(self):
    href = "https://rule34video.com/get_file/1/x/?download_filename=my%20clip.mp4"
    assert filename_from_href(href) == "my clip.mp4"

  def test_fallback_to_url_basename(self):
    # KVS 直链路径带尾斜杠，剥掉后 basename 才是真名
    href = "https://rule34video.com/get_file/54/abc/4306000/4306862/4306862_1080p.mp4/"
    assert filename_from_href(href) == "4306862_1080p.mp4"

  def test_nothing_usable(self):
    assert filename_from_href("https://rule34video.com/") == ""
    assert filename_from_href("") == ""


class TestLocalFilename:
  def test_download_filename_real_name(self):
    row = {"href": "https://rule34video.com/get_file/?download_filename=a_2160p.mp4",
           "text": "MP4 2160p"}
    assert local_filename(row, "4306862") == "a_2160p.mp4"

  def test_basename_when_param_missing(self):
    row = {"href": "https://rule34video.com/get_file/1/4306862_720p.mp4/",
           "text": "MP4 720p"}
    assert local_filename(row, "4306862") == "4306862_720p.mp4"

  def test_fallback_synthesizes_name(self):
    row = {"href": "", "text": "MP4 360p"}
    assert local_filename(row, "42") == "rule34_42_MP4 360p.mp4"


class TestIsWaitTimeout:
  def test_playwright_and_patchright_messages(self):
    # playwright / patchright 的 TimeoutError 不同类，按消息特征认
    assert is_wait_timeout(RuntimeError("Timeout 20000ms exceeded."))
    assert is_wait_timeout(RuntimeError("Timeout 60000ms exceeded while waiting"))

  def test_other_errors_not_matched(self):
    assert not is_wait_timeout(RuntimeError("net::ERR_CONNECTION_RESET"))
    assert not is_wait_timeout(RuntimeError("Download is starting"))
    assert not is_wait_timeout(RuntimeError(""))


class TestRegistry:
  def test_routing(self):
    a = adapter_for("https://rule34video.com/video/4306862/slug/")
    assert isinstance(a, Rule34Adapter)

  def test_www_routes(self):
    # host_of 剥 www.
    assert isinstance(
        adapter_for("https://www.rule34video.com/video/1/x/"), Rule34Adapter)

  def test_mirrors_not_in_scope(self):
    # 只接主域；镜像域不路由，留给后续逐家接入
    assert adapter_for("https://rule34video.net/video/1/x/") is None

  def test_all_hosts_registered(self):
    assert "rule34video.com" in all_hosts()
