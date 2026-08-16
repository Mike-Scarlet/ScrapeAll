
import cv2

decoder = cv2.wechat_qrcode.WeChatQRCode()
mat = cv2.imread("/home/ubuntu/Downloads/madana.png")
decoded = decoder.detectAndDecode(mat)
pass