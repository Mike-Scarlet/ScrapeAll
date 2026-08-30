
import pytest

from scrape_all.downloader.adapters import adapter_for
from scrape_all.downloader.adapters.mega import (
    MegaAdapter, _FOLDER_READY_SEL, _WAIT_MS, grid_row, parse_mega_url,
    parse_size_text, zip_est_size,
)


class TestProbeRenderWait:
  def test_render_wait_40s(self):
    # 探查渲染上限 40s：并发抢代理带宽时 folder SPA 20s 不够
    # （topic 314864 两次探查均在 20s 渲染超时转 exhausted）
    assert _WAIT_MS == 40000


# 网格视图行实测结构（2026-08 实抓，取证脚本 _mega_probe_diag.py 已删见 git 历史）：
# 根目录全是子文件夹的公开夹走 table.grid-table -> tr.megaListItem，
# 旧判据 a.mega-node.fm-item 一个都没有，probe 误报 unknown
_GRID_TDS = [
    {"cls": "space-maintainer-start", "txt": ""},
    {"cls": "", "txt": "DanceSex_美少女無罪_森亜るるか+6ALTs"},
    {"cls": "", "txt": ""},
    {"cls": "label", "txt": ""},
    {"cls": "owner", "txt": ""},
    {"cls": "time ad", "txt": "2026-05-22 20:42"},
    {"cls": "time md", "txt": ""},
    {"cls": "type", "txt": "文件夹"},
    {"cls": "size", "txt": "48.6\xa0MB"},
    {"cls": "hd-versions", "txt": ""},
    {"cls": "playtime", "txt": ""},
    {"cls": "fileLoc", "txt": "美少女無罪_森亜るるか"},
    {"cls": "grid-url-field own-data", "txt": ""},
    {"cls": "space-maintainer-end", "txt": ""},
]
_GRID_GB_TDS = [
    {"cls": "", "txt": "2026-07"},
    {"cls": "label", "txt": ""},
    {"cls": "type", "txt": "文件夹"},
    {"cls": "size", "txt": "8.47\xa0GB"},
]


class TestGridRow:
  def test_folder_row(self):
    row = grid_row({"id": "Q1sziQoa", "cls": "folder megaListItem ui-selectee",
                    "tds": _GRID_TDS})
    assert row == {"id": "Q1sziQoa",
                   "name": "DanceSex_美少女無罪_森亜るるか+6ALTs",
                   "size": 48_600_000, "is_dir": True}

  def test_gb_size(self):
    row = grid_row({"id": "9GwkWABY", "cls": "folder megaListItem ui-selectee",
                    "tds": _GRID_GB_TDS})
    assert row["size"] == 8_470_000_000 and row["is_dir"]

  def test_file_row_by_class(self):
    # is_dir 认 tr 类里的 folder token（td.type「文件夹」文案兜底）：
    # 文件行两者都没有 -> 非目录（真实文件行的 type 文案未实测，用空）
    tds = [dict(t) for t in _GRID_TDS]
    tds[7] = {"cls": "type", "txt": ""}
    row = grid_row({"id": "x1", "cls": "megaListItem ui-selectee",
                    "tds": tds})
    assert row["is_dir"] is False

  def test_row_without_name_dropped(self):
    tds = [dict(t) for t in _GRID_TDS]
    tds[1] = {"cls": "", "txt": ""}       # 名字列空 -> 整行丢弃
    assert grid_row({"id": "x2", "cls": "folder", "tds": tds}) is None

  def test_ready_selector_covers_both_views(self):
    # folder ready 判据必须同时认两种视图，缺一种就会再误报 unknown
    assert "mega-node" in _FOLDER_READY_SEL
    assert "megaListItem" in _FOLDER_READY_SEL


class TestZipEstSize:
  # 整夹 ZIP 等待窗口的体积估算：直下文件和优先；根目录全是子目录的夹
  # （网格视图）直下为 0，用地目录体积和兜底，否则 24GB 的 ZIP 会走 300s
  # 地板被活活掐死
  def test_files_sum_first(self):
    rows = [{"size": 100, "is_dir": False}, {"size": 50, "is_dir": False},
            {"size": 900, "is_dir": True}]
    assert zip_est_size(rows) == 150

  def test_all_dirs_fall_back_to_dir_sum(self):
    # 314864 实况：根下 2 子目录 48.6MB + 78.8MB
    rows = [{"size": 48_600_000, "is_dir": True},
            {"size": 78_800_000, "is_dir": True}]
    assert zip_est_size(rows) == 127_400_000

  def test_no_sizes_none(self):
    # 旧视图目录行读不到体积 -> None 走地板
    assert zip_est_size([{"size": None, "is_dir": True}]) is None
    assert zip_est_size([]) is None


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
