
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from scrape_all.downloader.adapters import adapter_for
from scrape_all.downloader.adapters.gofile import (
    GofileAdapter, name_from_aria, parse_gf_url, parse_size_text,
)


class TestParseGfUrl:
  def test_download_form(self):
    assert parse_gf_url("https://gofile.io/d/AuxExhX6") == "AuxExhX6"

  def test_with_trailing_path(self):
    assert parse_gf_url("https://gofile.io/d/UYEU7v#") == "UYEU7v"

  def test_other_form_rejected(self):
    assert parse_gf_url("https://gofile.io/w/foo") is None
    # host 校验归 matches()（注册表层），path 解析只认形态


class TestNameFromAria:
  def test_actions_for_prefix(self):
    assert name_from_aria("Actions for Kimiko.mp4") == "Kimiko.mp4"
    assert name_from_aria("Actions for  Rebirth 1.mp4") == "Rebirth 1.mp4"

  def test_no_prefix(self):
    assert name_from_aria("plain.mp4") == "plain.mp4"
    assert name_from_aria("") == ""


class TestParseSizeText:
  def test_units(self):
    # gofile 行文本是十进制显示（实测 283 MB 档）
    assert parse_size_text("Kimiko.mp4 2026年8月14日 23:10 69.2 MB Preview Download") == 69_200_000
    assert parse_size_text("283 MB") == 283_000_000
    assert parse_size_text("1.5 GB") == 1_500_000_000

  def test_unparseable(self):
    assert parse_size_text("Preview Download") is None
    assert parse_size_text("") is None
    assert parse_size_text(None) is None


class TestRegistry:
  def test_gofile_routing(self):
    a = adapter_for("https://gofile.io/d/AuxExhX6")
    assert isinstance(a, GofileAdapter)

  def test_hosts(self):
    assert GofileAdapter().matches("https://gofile.io/d/x")
    assert not GofileAdapter().matches("https://pixeldrain.com/u/x")
