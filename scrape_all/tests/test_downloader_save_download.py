import asyncio
import os

from scrape_all.downloader.engine import DownloadEngine
from scrape_all.downloader.fsutil import (
    resolve_save_path, same_size_or_unknown, url_token,
)


class FakeDownload:
  """playwright Download 替身：save_as 落真文件。sleep(0) 是关键——让出
  事件循环，模拟真实 save_as 的 await 窗口（并发 TOCTOU 就出在这个窗口）"""

  def __init__(self, content: bytes):
    self._content = content
    self.saved = []

  async def save_as(self, path):
    await asyncio.sleep(0)
    with open(path, "wb") as f:
      f.write(self._content)
    self.saved.append(path)


class TestUrlToken:
  def test_stable(self):
    assert url_token("https://x.test/a") == url_token("https://x.test/a")

  def test_default_length_hex(self):
    t = url_token("https://x.test/a")
    assert len(t) == 8
    int(t, 16)  # 合法 hex

  def test_different_urls_differ(self):
    assert url_token("https://x.test/a") != url_token("https://x.test/b")

  def test_custom_length(self):
    assert len(url_token("https://x.test/a", length=4)) == 4


class TestResolveSavePath:
  def test_free_name_untouched(self, tmp_path):
    out = resolve_save_path(str(tmp_path), "X.funscript", "abcd1234")
    assert out == os.path.join(str(tmp_path), "X.funscript")

  def test_occupied_name_gets_token_variant(self, tmp_path):
    (tmp_path / "X.funscript").write_bytes(b"old")
    out = resolve_save_path(str(tmp_path), "X.funscript", "abcd1234")
    assert out == os.path.join(str(tmp_path), "X.abcd1234.funscript")

  def test_token_variant_occupied_returns_it(self, tmp_path):
    # 同 token 重跑 = 同内容旧副本，返回 token 名覆盖自己（引擎 save_as 直接写）
    (tmp_path / "X.funscript").write_bytes(b"other")
    (tmp_path / "X.abcd1234.funscript").write_bytes(b"mine")
    out = resolve_save_path(str(tmp_path), "X.funscript", "abcd1234")
    assert out == os.path.join(str(tmp_path), "X.abcd1234.funscript")

  def test_no_extension_name(self, tmp_path):
    (tmp_path / "pack").write_bytes(b"old")
    out = resolve_save_path(str(tmp_path), "pack", "ab12cd34")
    assert out.endswith(os.path.join("", "pack.ab12cd34"))


class TestSameSizeOrUnknown:
  def test_expected_none_is_mirror(self, tmp_path):
    p = tmp_path / "X"
    p.write_bytes(b"12345")
    assert same_size_or_unknown(str(p), None)

  def test_size_match_is_mirror(self, tmp_path):
    p = tmp_path / "X"
    p.write_bytes(b"12345")
    assert same_size_or_unknown(str(p), 5)

  def test_size_mismatch_is_not_mirror(self, tmp_path):
    # 不同内容撞名：不能吃"已存在"跳过，得让引擎落 token 第二把
    p = tmp_path / "X"
    p.write_bytes(b"12345")
    assert not same_size_or_unknown(str(p), 6)

  def test_relative_tolerance_for_page_approx_sizes(self, tmp_path):
    # 页面人读体积（"39.5MB"）有解析误差：3% 容差内算镜像，容差外不是
    p = tmp_path / "X"
    p.write_bytes(b"\x00" * 1000)
    assert same_size_or_unknown(str(p), 1020, rel_tol=0.03)
    assert not same_size_or_unknown(str(p), 1100, rel_tol=0.03)
    # 默认 0 容差：头信息精确字节不做任何放水
    assert not same_size_or_unknown(str(p), 1001)

  def test_missing_file_not_mirror(self, tmp_path):
    assert not same_size_or_unknown(str(tmp_path / "nope"), 5)


class TestSaveDownload:
  def test_plain_save(self, tmp_path):
    eng = DownloadEngine()

    async def run():
      return await eng.save_download(FakeDownload(b"AAA"), str(tmp_path),
                                     "X.funscript", "t0k3n")

    p = asyncio.run(run())
    assert os.path.basename(p) == "X.funscript"
    assert (tmp_path / "X.funscript").read_bytes() == b"AAA"

  def test_name_sanitized(self, tmp_path):
    eng = DownloadEngine()

    async def run():
      return await eng.save_download(FakeDownload(b"AAA"), str(tmp_path),
                                     'a<b>.funscript', "t0k3n")

    p = asyncio.run(run())
    assert os.path.basename(p) == "a_b_.funscript"

  def test_collision_saves_second_copy_keeps_first(self, tmp_path):
    # 324422 实案回归：先下的 zip 不能被后下的同名 zip 覆盖
    eng = DownloadEngine()
    (tmp_path / "X.zip").write_bytes(b"OLD-299MB")

    async def run():
      return await eng.save_download(FakeDownload(b"NEW-2GB"), str(tmp_path),
                                     "X.zip", "ab12cd34")

    p = asyncio.run(run())
    assert os.path.basename(p) == "X.ab12cd34.zip"
    assert (tmp_path / "X.zip").read_bytes() == b"OLD-299MB"
    assert (tmp_path / "X.ab12cd34.zip").read_bytes() == b"NEW-2GB"

  def test_concurrent_same_name_both_survive(self, tmp_path):
    # 329965 实案回归：并发 worker 各自过了前置存在检查（当时都还不存在），
    # 落盘窗口互踩——锁内决策+落盘后，先完成者得本名、后到者得 token 第二把，
    # 两份内容都在盘上
    eng = DownloadEngine()

    async def run():
      d1, d2 = FakeDownload(b"AAA"), FakeDownload(b"BBB")
      t1 = asyncio.create_task(eng.save_download(d1, str(tmp_path),
                                                 "X.funscript", "t0k1"))
      t2 = asyncio.create_task(eng.save_download(d2, str(tmp_path),
                                                 "X.funscript", "t0k2"))
      return await asyncio.gather(t1, t2)

    p1, p2 = asyncio.run(run())
    names = {os.path.basename(p1), os.path.basename(p2)}
    assert "X.funscript" in names
    other = (names - {"X.funscript"}).pop()
    assert other.startswith("X.t0k") and other.endswith(".funscript")
    contents = {(tmp_path / "X.funscript").read_bytes(),
                (tmp_path / other).read_bytes()}
    assert contents == {b"AAA", b"BBB"}

  def test_same_token_rerun_overwrites_own_copy(self, tmp_path):
    # 同 URL 重跑：token 名就是自己的旧副本，覆盖无害
    eng = DownloadEngine()
    (tmp_path / "X.funscript").write_bytes(b"OTHER-LINK")
    (tmp_path / "X.ab12cd34.funscript").write_bytes(b"stale")

    async def run():
      return await eng.save_download(FakeDownload(b"fresh"), str(tmp_path),
                                     "X.funscript", "ab12cd34")

    p = asyncio.run(run())
    assert os.path.basename(p) == "X.ab12cd34.funscript"
    assert (tmp_path / "X.ab12cd34.funscript").read_bytes() == b"fresh"
    assert (tmp_path / "X.funscript").read_bytes() == b"OTHER-LINK"
