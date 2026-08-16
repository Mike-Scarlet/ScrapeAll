
from scrape_all.sites.cangku.qr import challenge_like, decode_qr_bytes


class FakeResp:
  def __init__(self, status, ctype):
    self.status = status
    self.ok = status < 400
    self.headers = {"content-type": ctype}


def test_decode_qr_bytes_invalid_inputs():
  assert decode_qr_bytes(b"") == ""
  assert decode_qr_bytes(b"not an image") == ""
  assert decode_qr_bytes(b"\x89PNG\r\n\x1a\ntruncated") == ""


def test_challenge_like_detection():
  # 图 URL 回 HTML 的 403/503 算挑战页；正常图响应和 None 不算
  assert challenge_like(FakeResp(403, "text/html; charset=UTF-8")) is True
  assert challenge_like(FakeResp(503, "text/html")) is True
  assert challenge_like(FakeResp(403, "image/webp")) is False
  assert challenge_like(FakeResp(200, "text/html")) is False
  assert challenge_like(None) is False
