
import urllib.request

import cv2
import numpy as np

url = "https://image.acg.lol/file/2026/08/07/mimu-26.07.webp"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
buf = urllib.request.urlopen(req, timeout=30).read()
mat = cv2.imdecode(np.frombuffer(buf, dtype=np.uint8), cv2.IMREAD_COLOR)

decoder = cv2.wechat_qrcode.WeChatQRCode()
decoded = decoder.detectAndDecode(mat)
print(decoded)
