
import pytest

from scrape_all.downloader.adapters import adapter_for
from scrape_all.downloader.adapters.mega import (
    MegaAdapter, parse_mega_url, parse_size_text,
)


class TestParseMegaUrl:
  def test_file_with_key(self):
    # 库内主流形态：密钥在 hash
    assert parse_mega_url(
        "https://mega.nz/file/Lj43zSwJ#YPDytvHKOPLU_bRHt-TgPg0") == ("file", "Lj43zSwJ")

  def test_folder_with_key(self):
    assert parse_mega_url(
        "https://mega.nz/folder/z0JzVIAY#mE2-P2BCbe5i1KjyZ8YfiQ") == ("folder", "z0JzVIAY")

  def test_folder_subnode_is_folder(self):
    # /folder/{id}/{子节点} 定位到夹内某文件，整夹处理
    assert parse_mega_url(
        "https://mega.nz/folder/z0JzVIAY/file/abcd1234#k") == ("folder", "z0JzVIAY")

  def test_no_key_still_parses(self):
    # 库内存在无 hash 的形态（如 RUsizRAL），路径照常解析
    assert parse_mega_url("https://mega.nz/folder/RUsizRAL") == ("folder", "RUsizRAL")

  def test_unknown_shape(self):
    assert parse_mega_url("https://mega.nz/d/abc") is None
    assert parse_mega_url("https://mega.nz/") is None
    assert parse_mega_url("https://example.com/file/abc") == ("file", "abc")  # host 校验归 matches()


class TestParseSizeText:
  def test_title_with_nbsp(self):
    # 行 title 实测格式：体积与名字之间是 nbsp
    assert parse_size_text("15\xa0KB [見ず水煮 Mizumizuni] 真紅.funscript") == 15_000
    assert parse_size_text("7\xa0KB [見ず水煮 Mizumizuni] 真紅.twist.funscript") == 7_000

  def test_video_title_resolution_prefix(self):
    # mp4 行 title 带分辨率/编码前缀，词边界锚定防止把 1080 读成体积
    assert parse_size_text(
        "1280x1080 @30fps isom/avc1 36\xa0MB [見ず水煮 mizumizuni] 真紅.mp4") == 36_000_000

  def test_plain_space_also_ok(self):
    assert parse_size_text("2 MB pg.gif") == 2_000_000

  def test_file_page_size_span(self):
    # file 页 .size 文本：nbsp 分隔、单位可能是小写
    assert parse_size_text("144.8\xa0mb") == 144_800_000
    assert parse_size_text("46.9\xa0MB") == 46_900_000

  def test_negative(self):
    assert parse_size_text("2 MB pg.gif 之外没有") == 2_000_000  # 只取第一个匹配
    assert parse_size_text("") is None
    assert parse_size_text(None) is None
    assert parse_size_text("30fps") is None


class TestRegistry:
  def test_mega_routing(self):
    assert isinstance(adapter_for("https://mega.nz/file/abc#k"), MegaAdapter)
    assert isinstance(adapter_for("https://mega.nz/folder/xyz#k"), MegaAdapter)

  def test_hosts(self):
    assert "mega.nz" in MegaAdapter.hosts
