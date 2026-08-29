# mega folder 探查诊断 v3（零下载）。v1/v2 结论已锁定：页面渲染正常（截图
# 佐证），是 ready 判据 a.mega-node.fm-item 匹配不上这种「根目录全是子
# 文件夹」的列表 DOM -> probe 误报 unknown。v3 抓真实 DOM：等列表渲染后，
# 深入 shadow DOM 找到行文本所在的最内层元素，打印它的祖先链（tag#id.class），
# 并统计候选选择器命中数，为 mega.py 换对选择器拿证据。
#   python playground/downloader/mega/_mega_probe_diag.py
import asyncio, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from python_general_lib.environment_setup.logging_setup import *
import logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

from config import DOWNLOADER_PROXY_SERVER
from scrape_all.browser.session import BrowserSession

CASES = [
  ("314864", "https://mega.nz/folder/NwcnGTbT#S1SNTBE9Xs8BJ36UM8KfAA", "美少女無罪"),
  ("320322", "https://mega.nz/folder/9DhEzYDS#EmoLKuto-e1i3XmoLN-7Tw", "archive"),
]
WAIT_S = 30          # 渲染观察窗：截图证明 ~8s 内已出列表，30s 绰绰有余

# 在页面里跑：深入 shadow DOM 找包含目标文本的最内层元素，打印祖先链
_JS = """async (needle) => {
  const chains = [];
  const chainOf = (el, top) => {
    const parts = [];
    let n = el, hops = 0;
    while (n && n !== document.body && hops < 8) {
      let s = n.tagName.toLowerCase();
      if (n.id) s += '#' + n.id;
      if (n.className && typeof n.className === 'string')
        s += '.' + n.className.trim().split(/\\s+/).slice(0, 3).join('.');
      parts.unshift(s);
      n = n.parentElement || (n.getRootNode() instanceof ShadowRoot
                              ? n.getRootNode().host : null);
      hops++;
    }
    return parts.join(' < ');
  };
  const scan = (root, inShadow) => {
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) scan(el.shadowRoot, true);
      const own = [...el.childNodes].filter(n => n.nodeType === 3)
                    .map(n => n.textContent.trim()).join('');
      if (needle && own.includes(needle) && chains.length < 6)
        chains.push((inShadow ? '[shadow] ' : '') + chainOf(el));
    }
  };
  scan(document, false);
  const sels = ['a.mega-node.fm-item', '.mega-node', 'a[class*="mega-node"]',
                'tr', '.fm-row', '[class*="fm-item"]', '.file-man-row',
                'a[href*="/folder/"]'];
  const counts = {};
  for (const s of sels) {
    let n = 0;
    const cnt = (root) => {
      n += root.querySelectorAll(s).length;
      for (const el of root.querySelectorAll('*')) if (el.shadowRoot) cnt(el.shadowRoot);
    };
    cnt(document);
    counts[s] = n;
  }
  return {chains, counts, title: document.title};
}"""

# 行内结构与下载按钮区（零点击）：前 3 行的 td 类名+文本；按钮/菜单元素
_JS2 = """async () => {
  const rows = [...document.querySelectorAll('tr.megaListItem')].slice(0, 3);
  const rowDump = rows.map(tr => ({
    id: tr.id, cls: tr.className,
    tds: [...tr.children].map(td => ({cls: td.className.trim(),
                                      txt: (td.innerText || '').trim().slice(0, 60)})),
  }));
  const btns = [...document.querySelectorAll('button, .fm-download-menu, [data-simpletip]')]
    .filter(el => (el.innerText || '').trim() || el.getAttribute('data-simpletip'))
    .slice(0, 25)
    .map(el => ({tag: el.tagName.toLowerCase(), cls: (el.className || '').toString().trim().slice(0, 60),
                 tip: el.getAttribute('data-simpletip'),
                 txt: (el.innerText || '').trim().slice(0, 30)}));
  return {rowDump, btns};
}"""


async def dump_one(session, tag, url, needle):
  page = await session.new_page()
  await page.goto(url, wait_until="domcontentloaded", timeout=30000)
  await page.wait_for_timeout(WAIT_S * 1000)
  out = await page.evaluate(_JS, needle)
  out2 = await page.evaluate(_JS2)
  print(f"[{tag}] title={out['title']!r}")
  print(f"[{tag}] 候选选择器命中（含 shadow DOM）:")
  for sel, n in out["counts"].items():
    print(f"    {n:4d}  {sel}")
  print(f"[{tag}] 前 3 行结构:")
  for r in out2["rowDump"]:
    print(f"    tr#{r['id']} .{r['cls']}")
    for td in r["tds"]:
      print(f"        td.{td['cls']}: {td['txt']!r}")
  print(f"[{tag}] 按钮/菜单元素（前 25）:")
  for b in out2["btns"]:
    print(f"    <{b['tag']} .{b['cls']}> tip={b['tip']!r} txt={b['txt']!r}")
  print(f"[{tag}] 含 {needle!r} 的最内层元素祖先链:")
  for c in out["chains"]:
    print(f"    {c}")
  await page.screenshot(path=os.path.join(
      os.path.dirname(os.path.abspath(__file__)), "_mega_diag", f"{tag}_v3.png"))
  await page.close()


async def main():
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  async with BrowserSession(DOWNLOADER_PROXY_SERVER) as session:
    for tag, url, needle in CASES:
      print(f"\n===== {tag} {url}")
      await dump_one(session, tag, url, needle)


if __name__ == "__main__":
  asyncio.run(main())
