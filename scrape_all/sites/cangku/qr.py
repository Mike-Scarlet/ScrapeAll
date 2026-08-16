
import time

import cv2
import numpy as np

# 二维码取图 + 解码。
# 取图必须走 playwright 浏览器页面（不要用 python http 客户端）：
#   - CDN 对代理出口 IP 拉黑、对 python TLS 指纹拉黑，真浏览器直连也可能吃 CF 挑战
#   - 图 URL 返回 403/503 + HTML 视为 Cloudflare 挑战：打印提示、停在那里等
#     用户在窗口里人工过验证，轮询直到放行（cf_clearance 留在持久化 profile 里）
#   - api.cangku.moe/favicon 代理不可用：返回 32x32 缩略图，解不出码
# 解码本身纯离线：wechat 解码器为主（艺术二维码——中间叠了人物图——也解得动，
# 216494 实测 QRCodeDetector 全预处理链都失败、wechat 原图直接出），
# QRCodeDetector 的多预处理兜底链保留，防个别构建缺 wechat 模块。

CHALLENGE_WAIT_TIMEOUT = 300.0   # CF 挑战等待上限（秒），等用户人工过验证
POLL_INTERVAL_MS = 3000

_wechat_det = None


def _get_wechat():
  """构建一次 wechat 解码器（不带 DNN 模型，传统算法路径）；无该模块的构建返回 None"""
  global _wechat_det
  if _wechat_det is None and hasattr(cv2, "wechat_qrcode_WeChatQRCode"):
    _wechat_det = cv2.wechat_qrcode_WeChatQRCode()
  return _wechat_det


def decode_qr_bytes(data: bytes) -> str:
  """cv2 解码：wechat 优先，失败再走 QRCodeDetector 兜底链
  （原图 -> OTSU 二值化 -> 2x/3x 放大）。
  站点二维码 300x300，个别对比度低/带压缩噪声，直接解会漏（224627 等实测）。"""
  if not data:
    return ""
  img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
  if img is None:
    return ""
  wechat = _get_wechat()
  if wechat is not None:
    try:
      texts, _ = wechat.detectAndDecode(img)
      if texts and texts[0]:
        return texts[0]
    except cv2.error:
      pass
  det = cv2.QRCodeDetector()
  text, _, _ = det.detectAndDecode(img)
  if text:
    return text
  gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
  _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
  for candidate in (otsu,
                    cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC),
                    cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)):
    text, _, _ = det.detectAndDecode(candidate)
    if text:
      return text
  return ""


def challenge_like(resp) -> bool:
  """图 URL 的响应像不像 CF 挑战/拦截页：403/503 且返回 HTML"""
  if resp is None or resp.ok:
    return False
  ctype = (resp.headers or {}).get("content-type", "")
  return resp.status in (403, 503) and ctype.startswith("text/html")


async def fetch_image(page, url: str,
                      challenge_timeout: float = CHALLENGE_WAIT_TIMEOUT) -> bytes:
  """在浏览器页面里取图；遇 CF 挑战则等人工过验证后重试，超时抛异常"""
  resp = await page.goto(url)
  if resp is not None and resp.ok:
    return await resp.body()
  if not challenge_like(resp):
    raise RuntimeError(f"image fetch failed: {resp.status if resp else 'no response'} {url}")

  print(f">> 疑似 Cloudflare 挑战（{url}）：请在浏览器窗口完成人机验证，"
        f"过后自动继续（最多等 {challenge_timeout:.0f}s）")
  deadline = time.monotonic() + challenge_timeout
  while time.monotonic() < deadline:
    await page.wait_for_timeout(POLL_INTERVAL_MS)
    resp = await page.goto(url)
    if resp is not None and resp.ok:
      return await resp.body()
  raise RuntimeError(f"cloudflare challenge wait timeout: {url}")
