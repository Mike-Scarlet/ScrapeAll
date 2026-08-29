
"""pixeldrain 联调 v4：页面 DOM 摸底（不点下载，只读结构）。

  /u/{id} 文件页：下载按钮是什么元素、文件名/大小显示在哪
  /l/{id} 列表页：文件行结构、每行有没有下载入口、有没有整单下载
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

DUMP_JS = """() => {
  const out = {title: document.title, url: location.href};
  // 下载候选：href 带 download 的链接、文本含 download 的按钮/链接
  out.dl_links = [...document.querySelectorAll('a[href*="download"]')]
    .slice(0, 8).map(a => ({tag: 'a', id: a.id, cls: a.className,
                            text: a.textContent.trim().slice(0, 40),
                            href: a.getAttribute('href')}));
  out.dl_buttons = [...document.querySelectorAll('button, a.btn, [role=button]')]
    .filter(el => /download/i.test(el.textContent))
    .slice(0, 8).map(el => ({tag: el.tagName, id: el.id, cls: el.className,
                             text: el.textContent.trim().slice(0, 40)}));
  // 体积类文本（页面上的文件大小展示）
  out.size_texts = [...document.querySelectorAll('*')]
    .filter(el => el.children.length === 0 &&
                  /^\\d+(\\.\\d+)?\\s*(bytes|KB|MB|GB|B)$/i.test(el.textContent.trim()))
    .slice(0, 5).map(el => ({tag: el.tagName, cls: el.className,
                             text: el.textContent.trim()}));
  return out;
}"""

LIST_DUMP_JS = """() => {
  const out = {title: document.title, url: location.href};
  // 列表页文件行：找指向 /u/ 的链接（每行文件入口）
  out.file_links = [...document.querySelectorAll('a[href*="/u/"]')]
    .slice(0, 6).map(a => ({text: a.textContent.trim().slice(0, 50),
                            href: a.getAttribute('href'),
                            row_cls: (a.closest('li,tr,div[class]')||{}).className}));
  out.dl_links = [...document.querySelectorAll('a[href*="download"]')]
    .slice(0, 8).map(a => ({text: a.textContent.trim().slice(0, 30),
                            href: a.getAttribute('href')}));
  return out;
}"""


async def inspect(engine, url, dump_js, label):
  page = await engine.context.new_page()
  try:
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
    await page.wait_for_timeout(4000)   # 等客户端渲染
    r = await page.evaluate(dump_js)
    print(f"===== {label} {url}")
    for k, v in r.items():
      print(f"  {k}: {v}")
  except Exception as e:
    print(f"===== {label} {url} -> 失败 {e}")
  finally:
    await page.close()


async def main():
  async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
    # 文件页：14MB 那个（安全），列表页：活的 Mantis-X
    await inspect(engine, "https://pixeldrain.com/u/QG5Pqjpq", DUMP_JS, "文件页")
    await inspect(engine, "https://pixeldrain.com/l/dQotgt6u", LIST_DUMP_JS, "列表页")
    # 死链页形态对照
    await inspect(engine, "https://pixeldrain.com/u/kV6Aqw71", DUMP_JS, "死文件页")
    print("\n保持 30s 供观察", flush=True)
    await asyncio.sleep(30)


asyncio.run(main())
