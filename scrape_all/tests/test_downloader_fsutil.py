
import pytest

from scrape_all.downloader.fsutil import sanitize_filename, topic_dir_name


class TestSanitizeFilename:
  def test_illegal_chars_replaced(self):
    out = sanitize_filename('a<b>c:d"e|f?g*h/i\\j')
    for c in '<>:"|?*/\\':
      assert c not in out
    assert out.count("_") >= 8

  def test_control_chars_replaced(self):
    assert "\x00" not in sanitize_filename("a\x00b\x1fc")

  def test_trailing_dots_and_spaces_stripped(self):
    assert sanitize_filename("name.. . ") == "name"
    assert sanitize_filename("  name  ") == "name"

  def test_whitespace_collapsed(self):
    assert sanitize_filename("a \t\n b") == "a b"

  def test_empty_and_all_illegal(self):
    assert sanitize_filename("") == "unnamed"
    assert sanitize_filename("???") == "unnamed"
    assert sanitize_filename(" . ") == "unnamed"

  def test_windows_reserved_names(self):
    assert sanitize_filename("CON") == "_CON"
    assert sanitize_filename("com1.funscript") == "_com1.funscript"
    assert sanitize_filename("NUL") == "_NUL"

  def test_normal_name_untouched(self):
    name = "dokidoki little ooyasan ep.1.funscript"
    assert sanitize_filename(name) == name

  def test_unicode_kept(self):
    # 标题里的 emoji/中文都是合法文件名字符，保留
    assert sanitize_filename("🎬 Video Link.funscript") == "🎬 Video Link.funscript"
    assert sanitize_filename("东京都北区.pk") == "东京都北区.pk"

  def test_long_name_truncated_keeps_ext(self):
    name = "x" * 300 + ".funscript"
    out = sanitize_filename(name)
    assert len(out) <= 120
    assert out.endswith(".funscript")

  def test_overlong_ext_treated_as_stem(self):
    # 扩展名超过 16 字符说明 splitext 切错了位置（查询串粘在路径里），不按扩展名保
    name = "name." + "y" * 30
    out = sanitize_filename(name)
    assert len(out) <= 120

  def test_truncation_never_leaves_empty(self):
    assert sanitize_filename(".") == "unnamed"


class TestTopicDirName:
  def test_basic(self):
    out = topic_dir_name(11213, "dokidoki little ooyasan")
    assert out == "11213_dokidoki little ooyasan"

  def test_title_sanitized(self):
    out = topic_dir_name(1, 'what? "no" <way>')
    for c in '<>:"?':
      assert c not in out

  def test_long_title_truncated(self):
    out = topic_dir_name(42, "t" * 500)
    assert len(out) <= 83   # "42_" + 80

  def test_empty_title(self):
    assert topic_dir_name(7, "") == "7_unnamed"
