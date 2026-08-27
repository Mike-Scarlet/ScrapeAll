
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from scrape_all.downloader.adapters.base import (
    DL_TIMEOUT_HEADROOM_S, DL_TIMEOUT_SPEED_BPS, dl_wait_ms, timeout_for_size,
)
from scrape_all.downloader.adapters.catbox import CatboxAdapter
from scrape_all.downloader.adapters.eros_uploads import ErosUploadsAdapter
from scrape_all.downloader.adapters.pixeldrain import est_size_from_stats

CATBOX_BIG = "https://files.catbox.moe/9p4z2f.mp4"
CATBOX_BIG_SIZE = 194_677_097    # 2026-08-26 实际翻车的 185.6MB


class TestTimeoutForSize:
  def test_none_or_zero_falls_back_to_base(self):
    assert timeout_for_size(None, 120) == 120
    assert timeout_for_size(0, 60) == 60

  def test_small_file_stays_at_floor(self):
    # 20KB@200KB/s 推算远小于 120s 地板
    assert timeout_for_size(20 * 1024, 120) == 120

  def test_big_file_scales_at_floor_speed(self):
    t = timeout_for_size(CATBOX_BIG_SIZE, 120)
    assert t == CATBOX_BIG_SIZE / DL_TIMEOUT_SPEED_BPS + DL_TIMEOUT_HEADROOM_S
    assert t > 900      # 185.6MB@200KB/s 至少 15 分钟

  def test_monotonic_in_size(self):
    assert timeout_for_size(10 ** 9, 120) < timeout_for_size(3 * 10 ** 9, 120)

  def test_base_is_floor(self):
    # mega 的 300s 地板：小体积不缩水
    assert timeout_for_size(10 ** 6, 300) == 300

  def test_dl_wait_ms(self):
    assert dl_wait_ms(None, 60) == 60_000
    assert dl_wait_ms(CATBOX_BIG_SIZE, 60) == \
        int(timeout_for_size(CATBOX_BIG_SIZE, 60) * 1000)


class FakePrimitiveEngine:
  """catbox / eros_uploads 走的引擎原语最小假体：记录调用参数、落个空文件
  （adapter download 成功路径会 getsize，假体必须真建文件）"""

  def __init__(self, status: int = 206, headers: dict | None = None):
    self._status = status
    self._headers = headers or {}
    self.blob_calls = []      # (url, timeout_s)
    self.direct_calls = []    # (url, timeout_s)

  async def probe_headers(self, url, timeout_s=30.0, park_url=None):
    return {"status": self._status, "headers": self._headers}

  async def blob_download(self, url, dest_dir, filename=None,
                          timeout_s=None, park_url=None):
    self.blob_calls.append((url, timeout_s))
    dest = os.path.join(dest_dir, filename or "f.bin")
    open(dest, "wb").close()
    return dest

  async def direct_download(self, url, dest_dir, filename=None, timeout_s=None):
    self.direct_calls.append((url, timeout_s))
    dest = os.path.join(dest_dir, filename or "f.bin")
    open(dest, "wb").close()
    return dest


class TestCatboxTimeout:
  def test_blob_timeout_scales_with_probe_size(self, tmp_path):
    eng = FakePrimitiveEngine(206, {"content-range":
                                    f"bytes 0-0/{CATBOX_BIG_SIZE}"})
    res = asyncio.run(CatboxAdapter().download(eng, CATBOX_BIG, str(tmp_path)))
    assert res.status == "downloaded"
    assert eng.blob_calls == [(CATBOX_BIG, timeout_for_size(CATBOX_BIG_SIZE))]

  def test_small_file_keeps_floor(self, tmp_path):
    eng = FakePrimitiveEngine(206, {"content-length": "20480"})
    res = asyncio.run(CatboxAdapter().download(
        eng, "https://files.catbox.moe/small.mp4", str(tmp_path)))
    assert res.status == "downloaded"
    assert eng.blob_calls[0][1] == 120.0

  def test_dead_never_reaches_download(self, tmp_path):
    eng = FakePrimitiveEngine(404)
    res = asyncio.run(CatboxAdapter().download(
        eng, "https://files.catbox.moe/gone.mp4", str(tmp_path)))
    assert res.status == "dead"
    assert eng.blob_calls == []


class TestErosUploadsTimeout:
  def test_direct_timeout_scales_with_probe_size(self, tmp_path):
    eng = FakePrimitiveEngine(206, {
        "content-disposition": 'attachment; filename="clip.mp4"',
        "content-range": "bytes 0-0/500000000"})
    res = asyncio.run(ErosUploadsAdapter().download(
        eng, "https://discuss.eroscripts.com/uploads/short-url/xyz", str(tmp_path)))
    assert res.status == "downloaded"
    assert eng.direct_calls[0][1] == timeout_for_size(500_000_000)

  def test_small_attachment_keeps_floor(self, tmp_path):
    eng = FakePrimitiveEngine(206, {
        "content-disposition": 'attachment; filename="s.funscript"',
        "content-length": "17906"})
    # funscript 落盘后要过 JSON 校验，假体写个合法最小结构
    real = eng.direct_download

    async def write_funscript(url, dest_dir, filename=None, timeout_s=None):
      dest = await real(url, dest_dir, filename, timeout_s)
      with open(dest, "w", encoding="utf-8") as f:
        f.write('{"actions": [], "version": "1.0"}')
      return dest
    eng.direct_download = write_funscript
    res = asyncio.run(ErosUploadsAdapter().download(
        eng, "https://discuss.eroscripts.com/uploads/short-url/abc.funscript",
        str(tmp_path)))
    assert res.status == "downloaded"
    assert eng.direct_calls[0][1] == 120.0


class TestPixeldrainEstSize:
  def test_file_page_single_stat(self):
    assert est_size_from_stats([14_000_000]) == 14_000_000

  def test_list_page_sums_rows(self):
    # 列表页 .stat 是逐文件体积，求和≈整包 zip 大小
    assert est_size_from_stats([14_000_000, 51_000_000]) == 65_000_000

  def test_empty_is_none(self):
    assert est_size_from_stats([]) is None
