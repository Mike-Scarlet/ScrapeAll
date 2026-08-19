
import argparse, asyncio, os, sys

# scrape_all/browser/login_shell.py -> scrape_all/browser -> scrape_all -> project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scrape_all.browser.session import BrowserSession
from config import CANGKU_PROXY_SERVER

# 起一个带持久化 profile（browser_session/）的有头浏览器，然后挂住等人工操作：
# 去窗口里登录各站点，cookie/登录态写进同一份 profile，之后抓取直接复用。
#
#   python scrape_all/browser/login_shell.py [URL ...]
#
# 选项：
#   --proxy cangku|<server>   走代理登录。cf_clearance 这类 cookie 绑出口 IP，
#                             要和之后抓取用同一代理才有效
#   --stealth                 用 patchright 起浏览器（和 cangku 抓取同上下文）
#
# 登录完回控制台按回车（Ctrl+C 也行）退出，脚本负责正常收尾让 profile 落盘。
# 尽量别直接叉掉浏览器窗口退出——万一 profile 没写完，登录就白做了。

async def main():
  parser = argparse.ArgumentParser(description="起浏览器等人工登录（写持久化 profile）")
  parser.add_argument("urls", nargs="*", help="启动时顺手打开的站点 URL")
  args = parser.parse_args()

  async with BrowserSession(
      # proxy_server=CANGKU_PROXY_SERVER, 
      stealth=False
      ) as session:
    for url in args.urls:
      page = await session.new_page()
      try:
        await page.goto(url)
      except Exception as e:
        print(f"打开 {url} 失败：{e}（在窗口里手动访问即可）")

    print("浏览器已就绪，去窗口里登录吧。完成后回这里按回车退出...")
    try:
      input()
    except (KeyboardInterrupt, EOFError):
      pass

    try:
      hosts = sorted({c["domain"] for c in await session.context.cookies()})
      print(f"profile 里现有 cookie 域：{hosts}")
    except Exception:
      pass   # 窗口已被手动关掉时查不了，不影响收尾

  print("profile 已保存，之后抓取直接复用登录态")

asyncio.run(main())
