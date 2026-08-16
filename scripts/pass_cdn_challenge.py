
import argparse, asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
import logging
logging.basicConfig(
  level=logging.NOTSET,
  format="[%(asctime)s] %(message)s",
)

from scrape_all.browser.session import BrowserSession
from config import CANGKU_PROXY_SERVER

# 手动过图床的 Cloudflare 挑战，把 cf_clearance 存进持久化 profile（browser_session/）。
# 用和抓取完全一致的上下文（同 profile + 同代理），这样以后浏览器里取图不再吃挑战。
#
#   python scripts/pass_cdn_challenge.py [图床URL]
#
# 行为：打开浏览器到目标 URL（会显示挑战页），你在窗口里完成人机验证，
# 页面自动刷新成 200 图像即成功（不要手动关窗口，脚本自己收尾退出）。
# 挑战是按域名的，换图床域名时再用对应 URL 跑一次。

DEFAULT_URL = "https://cdnimg.hxcy.top/uploads/2026/07/01SxI878ee48fc8786935.webp"
WAIT_TIMEOUT = 480   # 等人工过验证的上限（秒）


async def main():
  parser = argparse.ArgumentParser(description="人工过 CDN Cloudflare 挑战")
  parser.add_argument("url", nargs="?", default=DEFAULT_URL, help="图床 URL（默认 cdnimg.hxcy.top 样例）")
  args = parser.parse_args()

  async with BrowserSession(CANGKU_PROXY_SERVER, stealth=True) as session:
    page = await session.new_page()
    try:
      resp = await page.goto(args.url)
      if resp is not None and resp.ok:
        print("already 200：clearance 仍有效，不用过挑战")
        return
      print(f"status={resp.status if resp else 'no-response'}，请在窗口完成人机验证（不要关窗口）...")

      done = asyncio.Event()

      def on_response(r):
        if r.url.split("?")[0] == args.url.split("?")[0] and r.status == 200:
          done.set()

      page.on("response", on_response)
      try:
        await asyncio.wait_for(done.wait(), timeout=WAIT_TIMEOUT)
      except asyncio.TimeoutError:
        print(f"超时（{WAIT_TIMEOUT}s）没等到 200：挑战没过完，或该代理出口被硬拦")
        return
      await page.wait_for_timeout(2000)   # 等 cookie 落定再查

      host = args.url.split("/")[2]
      cookies = [c["name"] for c in await session.context.cookies(args.url)]
      print(f"OK：{host} 200，profile 里该域 cookies: {cookies}")
    finally:
      await page.close()

  print("profile 已保存，之后浏览器取图应免挑战")

asyncio.run(main())
