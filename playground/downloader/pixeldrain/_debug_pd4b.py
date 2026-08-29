
"""pixeldrain v4b：列表页 DOM 深挖——全量链接、行容器、滚动懒加载。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

DUMP_JS = """() => {
  const out = {title: document.title};
  out.all_links = [...document.querySelectorAll('a[href]')]
    .slice(0, 40)
    .map(a => ({t: a.textContent.trim().slice(0, 45), h: a.getAttribute('href')}));
  out.buttons = [...document.querySelectorAll('button')]
    .slice(0, 15)
    .map(b => ({t: b.textContent.trim().slice(0, 40), cls: b.className.slice(0, 50)}));
  // 主内容区顶层结构
  const main = document.querySelector('main, #app, .page');
  out.main_children = main ? [...main.children].slice(0, 10).map(
      c => c.tagName + '.' + String(c.className).slice(0, 40)) : null;
  // 疑似文件名的文本节点（mp4/zip 等）
  out.file_like = [...document.querySelectorAll('a, span, div')]
    .filter(el => el.children.length === 0 && /\\.(mp4|mkv|zip|7z|rar|mp3)/i.test(el.textContent))
    .slice(0, 8).map(el => ({tag: el.tagName, t: el.textContent.trim().slice(0, 60)}));
  return out;
}"""


async def main():
  async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
    page = await engine.context.new_page()
    try:
      resp = await page.goto("https://pixeldrain.com/l/dQotgt6u",
                             wait_until="domcontentloaded", timeout=25000)
      await page.wait_for_timeout(5000)
      await page.mouse.wheel(0, 2000)   # 触发懒加载
      await page.wait_for_timeout(3000)
      r = await page.evaluate(DUMP_JS)
      for k, v in r.items():
        print(f"{k}:")
        if isinstance(v, list):
          for item in v:
            print(f"    {item}")
        else:
            print(f"    {v}")
    except Exception as e:
      print(f"失败 {e}")
    finally:
      await page.close()
    await asyncio.sleep(15)


asyncio.run(main())
