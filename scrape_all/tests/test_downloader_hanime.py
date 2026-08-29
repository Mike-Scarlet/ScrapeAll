
from scrape_all.downloader.adapters import adapter_for, all_hosts
from scrape_all.downloader.adapters.hanime import (
    HanimeAdapter, is_download_nav_error, local_filename, parse_hanime_url,
    pick_best_row, resolve_dest, row_resolution,
)


class TestParseHanimeUrl:
  def test_watch_form(self):
    assert parse_hanime_url("https://hanime1.me/watch?v=404842") == "404842"

  def test_download_form(self):
    # 库里少量帖子直接贴 download 页，同一 id 空间
    assert parse_hanime_url("https://hanime1.me/download?v=21649") == "21649"

  def test_extra_query_params(self):
    assert parse_hanime_url("https://hanime1.me/watch?v=85349&t=12") == "85349"
    assert parse_hanime_url("http://hanime1.me/watch?v=1") == "1"

  def test_non_video_forms(self):
    # 搜索页等不是视频，probe/download 都不该碰
    assert parse_hanime_url(
        "https://hanime1.me/search?query=custom%2Budon&type=") is None
    assert parse_hanime_url("https://hanime1.me/") is None
    assert parse_hanime_url("https://hanime1.me/playlist?p=1") is None

  def test_missing_v(self):
    assert parse_hanime_url("https://hanime1.me/watch") is None
    assert parse_hanime_url("https://hanime1.me/watch?w=404842") is None


class TestPickBestRow:
  def test_highest_resolution_wins(self):
    rows = [
        {"quality": "全高清畫質 (1080p)"},
        {"quality": "高清畫質 (720p)"},
        {"quality": "標準畫質 (480p)"},
    ]
    assert pick_best_row(rows) == rows[0]

  def test_unordered_rows(self):
    rows = [
        {"quality": "標準畫質 (480p)"},
        {"quality": "全高清畫質 (1080p)"},
    ]
    assert pick_best_row(rows) == rows[1]

  def test_unparseable_label_falls_back_to_page_order(self):
    # 画质文本认不出分辨率时保页面原序（首行在前）
    rows = [{"quality": "高清"}, {"quality": "標準"}]
    assert pick_best_row(rows) == rows[0]

  def test_parseable_beats_unparseable(self):
    rows = [{"quality": "特殊畫質"}, {"quality": "(480p)"}]
    assert pick_best_row(rows) == rows[1]

  def test_empty(self):
    assert pick_best_row([]) is None

  def test_row_resolution(self):
    assert row_resolution("全高清畫質 (1080p)") == 1080
    assert row_resolution("720p") == 720
    assert row_resolution("N/A") == -1
    assert row_resolution("") == -1


class TestLocalFilename:
  def test_name_plus_url_ext(self):
    # download 属性真名不带扩展名，从 CDN 路径补 .mp4
    row = {"url": "https://vdownload-7.example/404842-1080p.mp4?token=x&expires=1",
           "name": "[パントン] 大神環 | Ogami Tamaki",
           "quality": "全高清畫質 (1080p)", "ext": "mp4"}
    assert local_filename(row, "404842") == "[パントン] 大神環 | Ogami Tamaki.mp4"

  def test_ext_from_type_column_when_url_has_none(self):
    row = {"url": "https://cdn.example/dl?token=x", "name": "Some Title",
           "quality": "(720p)", "ext": "MP4"}
    assert local_filename(row, "1") == "Some Title.mp4"

  def test_name_keeps_existing_ext(self):
    row = {"url": "https://cdn.example/a.mkv", "name": "clip.mp4",
           "quality": "(480p)", "ext": "mp4"}
    assert local_filename(row, "1") == "clip.mp4"

  def test_name_fallback(self):
    row = {"url": "https://cdn.example/a.mp4", "name": "",
           "quality": "全高清畫質 (1080p)", "ext": "mp4"}
    assert local_filename(row, "404842") == "hanime_404842_全高清畫質 (1080p).mp4"

  def test_no_ext_anywhere(self):
    row = {"url": "https://cdn.example/a", "name": "T", "quality": "(720p)", "ext": ""}
    assert local_filename(row, "1") == "T"


class TestResolveDest:
  def test_fresh_name(self, tmp_path):
    dest, exists = resolve_dest(str(tmp_path), "ケイ.mp4", "404683")
    assert (dest, exists) == (str(tmp_path / "ケイ.mp4"), False)

  def test_same_name_collision_gets_vid_suffix(self, tmp_path):
    # 同系列不同视频同名：第一把已落盘，第二把改 {stem}.{vid}{ext}
    (tmp_path / "ケイ.mp4").write_bytes(b"x")
    dest, exists = resolve_dest(str(tmp_path), "ケイ.mp4", "404683")
    assert (dest, exists) == (str(tmp_path / "ケイ.404683.mp4"), False)

  def test_both_names_exist_is_real_dup(self, tmp_path):
    (tmp_path / "ケイ.mp4").write_bytes(b"x")
    (tmp_path / "ケイ.404683.mp4").write_bytes(b"x")
    dest, exists = resolve_dest(str(tmp_path), "ケイ.mp4", "404683")
    assert (dest, exists) == (str(tmp_path / "ケイ.mp4"), True)


class TestIsDownloadNavError:
  def test_attachment_nav_message(self):
    # playwright/patchright 取消导航时的真实消息形态
    assert is_download_nav_error(RuntimeError("Download is starting"))

  def test_other_errors_not_matched(self):
    assert not is_download_nav_error(RuntimeError("net::ERR_CONNECTION_RESET"))
    assert not is_download_nav_error(RuntimeError("Timeout 30000ms exceeded"))
    assert not is_download_nav_error(RuntimeError(""))

  def test_message_embedded_in_log(self):
    e = RuntimeError("Page.goto: Download is starting\nCall log:\n  navigating")
    assert is_download_nav_error(e)


class TestRegistry:
  def test_routing(self):
    a = adapter_for("https://hanime1.me/watch?v=404842")
    assert isinstance(a, HanimeAdapter)
    assert isinstance(adapter_for("https://hanime1.me/download?v=1"), HanimeAdapter)

  def test_mirrors_not_in_scope(self):
    # 只接主域：镜像域（hanime1.com 等）不路由，留给后续逐家接入
    assert adapter_for("https://hanime1.com/watch?v=1") is None

  def test_all_hosts_registered(self):
    assert "hanime1.me" in all_hosts()
