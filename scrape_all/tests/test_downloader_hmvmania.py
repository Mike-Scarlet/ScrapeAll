
from scrape_all.downloader.adapters import adapter_for, all_hosts
from scrape_all.downloader.adapters.hmvmania import (
    HmvmaniaAdapter, local_filename, parse_hmvmania_url, pick_best_row,
    row_resolution,
)


class TestParseHmvmaniaUrl:
  def test_video_form_with_trailing_slash(self):
    assert parse_hmvmania_url(
        "https://hmvmania.com/video/hmvhero69-cc005-beethoven-legend-clover/"
    ) == "hmvhero69-cc005-beethoven-legend-clover"

  def test_no_trailing_slash(self):
    assert parse_hmvmania_url(
        "https://hmvmania.com/video/pixelfh-fap-hero-beats-3-round-3") == \
        "pixelfh-fap-hero-beats-3-round-3"

  def test_player_fragment_is_fragment_not_path(self):
    # 库里真实形态：#/?playlistId=0&videoId=0 是播放器状态，全在 fragment 里
    assert parse_hmvmania_url(
        "https://hmvmania.com/video/zen-ageplay/#/?playlistId=0&videoId=0"
    ) == "zen-ageplay"

  def test_query_params(self):
    assert parse_hmvmania_url("https://hmvmania.com/video/x/?t=1") == "x"

  def test_non_video_forms(self):
    # /author/、分类页、wp-content 直链、根都不是视频页，probe/download 都不该碰
    assert parse_hmvmania_url("https://hmvmania.com/author/hmvhero69/") is None
    assert parse_hmvmania_url("https://hmvmania.com/video-category/hmv/") is None
    assert parse_hmvmania_url(
        "https://hmvmania.com/wp-content/uploads/2021/01/hmv_1080p_x.mp4?_=1"
    ) is None
    assert parse_hmvmania_url("https://hmvmania.com/") is None

  def test_nested_path_segments(self):
    # /video/a/b/ 不是单 slug 视频页
    assert parse_hmvmania_url("https://hmvmania.com/video/a/b/") is None


class TestRowResolution:
  def test_av1_prefix_naming(self):
    # 站点自命名：av1_<分辨率>p_<真名>.mp4（锚文本恒为 "DL"，只认 href）
    assert row_resolution(
        "https://hmvmania.com/wp-content/uploads/2021/01/"
        "av1_1080p_hmvhero69-CC005-Beethoven-Legend-Clover.mp4") == 1080
    assert row_resolution(
        "https://hmvmania.com/wp-content/uploads/2021/01/"
        "av1_720p_Nanashi-clickbait.mp4") == 720
    assert row_resolution(
        "https://hmvmania.com/wp-content/uploads/2021/01/"
        "av1_2160p_RbynessXI-Dick.mp4") == 2160

  def test_resolution_as_suffix(self):
    # 个别命名分辨率在词尾（RADICAL-LITTLE-MAN-Faphero-1080p.mp4）
    assert row_resolution(
        "https://hmvmania.com/wp-content/uploads/x/"
        "RADICAL-LITTLE-MAN-Faphero-1080p.mp4") == 1080

  def test_unmarked_name(self):
    # 无标记真名（Zen-AGEPLAY.mp4）认不出，选档走首行兜底
    assert row_resolution(
        "https://hmvmania.com/wp-content/uploads/x/Zen-AGEPLAY.mp4") == -1

  def test_unparseable(self):
    assert row_resolution("") == -1
    assert row_resolution(None) == -1
    assert row_resolution("https://hmvmania.com/") == -1

  def test_player_template_href_not_confused(self):
    # 播放器 JS 模板的 href="{{ data.url }}" 不是直链，认不出
    assert row_resolution("{{ data.url }}") == -1


class TestPickBestRow:
  def _rows(self, *hrefs):
    return [{"i": i, "text": "DL", "href": h} for i, h in enumerate(hrefs)]

  def test_highest_within_cap_wins(self):
    # 2160p 在 1080p 上限之外，上限内最高的是 1080p
    rows = self._rows(
        "https://hmvmania.com/wp-content/uploads/x/av1_2160p_a.mp4",
        "https://hmvmania.com/wp-content/uploads/x/av1_1080p_b.mp4",
        "https://hmvmania.com/wp-content/uploads/x/av1_720p_c.mp4")
    assert pick_best_row(rows) is rows[1]

  def test_unordered_rows(self):
    rows = self._rows(
        "https://hmvmania.com/wp-content/uploads/x/av1_480p_a.mp4",
        "https://hmvmania.com/wp-content/uploads/x/av1_2160p_b.mp4",
        "https://hmvmania.com/wp-content/uploads/x/av1_720p_c.mp4")
    assert pick_best_row(rows) is rows[2]

  def test_all_above_cap_falls_back_to_first_row(self):
    # 上限是选档偏好不是硬墙：全超上限时保页面原序兜底（note 里可见）
    rows = self._rows(
        "https://hmvmania.com/wp-content/uploads/x/av1_2160p_a.mp4",
        "https://hmvmania.com/wp-content/uploads/x/av1_1440p_b.mp4")
    assert pick_best_row(rows) is rows[0]

  def test_unparseable_falls_back_to_page_order(self):
    # 12 页抽查全单档且个别无标记（Zen-AGEPLAY.mp4），首行兜底即它本身
    rows = self._rows("https://hmvmania.com/wp-content/uploads/x/Zen-AGEPLAY.mp4")
    assert pick_best_row(rows) is rows[0]

  def test_parseable_beats_unparseable(self):
    rows = self._rows(
        "https://hmvmania.com/wp-content/uploads/x/Zen-AGEPLAY.mp4",
        "https://hmvmania.com/wp-content/uploads/x/av1_480p_b.mp4")
    assert pick_best_row(rows) is rows[1]

  def test_same_resolution_keeps_page_order(self):
    rows = self._rows(
        "https://hmvmania.com/wp-content/uploads/x/av1_1080p_a.mp4",
        "https://hmvmania.com/wp-content/uploads/x/av1_1080p_b.mp4")
    assert pick_best_row(rows) is rows[0]

  def test_empty(self):
    assert pick_best_row([]) is None


class TestLocalFilename:
  def test_href_basename_is_the_name(self):
    # 直链 basename 即站点自命名真名，跨会话稳定（幂等靠它）
    row = {"href": "https://hmvmania.com/wp-content/uploads/2021/01/"
                  "av1_1080p_hmvhero69-CC005-Beethoven-Legend-Clover.mp4"}
    assert local_filename(row, "slug") == \
        "av1_1080p_hmvhero69-CC005-Beethoven-Legend-Clover.mp4"

  def test_fallback_synthesizes_name(self):
    assert local_filename({"href": ""}, "zen-ageplay") == "hmvmania_zen-ageplay.mp4"

  def test_fallback_when_href_missing(self):
    assert local_filename({}, "x") == "hmvmania_x.mp4"


class TestRegistry:
  def test_routing(self):
    a = adapter_for("https://hmvmania.com/video/hmvhero69-cc005-beethoven-legend-clover/")
    assert isinstance(a, HmvmaniaAdapter)

  def test_www_routes(self):
    # host_of 剥 www.
    assert isinstance(
        adapter_for("https://www.hmvmania.com/video/x/"), HmvmaniaAdapter)

  def test_other_domains_not_in_scope(self):
    assert adapter_for("https://hmvmania.net/video/x/") is None

  def test_all_hosts_registered(self):
    assert "hmvmania.com" in all_hosts()
