
"""mega 观察轮三：点击实验（用户已批准"点击→下载事件→cancel"套路）。

关键背景（用户经验）：mega 先在页面内把文件拉完解密，最后才弹下载框——
cancel 前流量已花。所以只点 KB 级小文件。

  1) folder 真紅 hS0XmIgL（总 39.5MB）：扒文件行结构 -> 右键最小的
     .funscript 行 -> 找菜单里的"下载" -> 点 -> 等下载事件 -> cancel。
     流量预算 ≈ 该 funscript 本身（KB 级）
  2) file 页 mh4QhYLZ（144.8MB）：只扒下载按钮 DOM，不点

共 2 次页面加载 + 1 次小文件点击。"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_PROXY_SERVER

FOLDER = "https://mega.nz/folder/hS0XmIgL#afw2rN0BPH9pURsw7kIeTw"
FILEPG = "https://mega.nz/file/mh4QhYLZ#ScK1HkZbBymamt6dPfIipHicde4qNTRS17rsCHFMSrw"


def squeeze(s: str, n: int = 500) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:n]


_SIZE_MULT = {"B": 1, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3}


def parse_size(t):
    m = re.search(r"([\d.]+)\s*(B|KB|MB|GB)", t or "")
    if not m:
        return None
    return int(float(m.group(1)) * _SIZE_MULT[m.group(2)])


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        # ---- 1) folder：行结构 + 右键下载实验 ----
        page = await engine.context.new_page()
        storage_hits = []
        page.on("request", lambda r: storage_hits.append(r.url[:100])
                if "userstorage.mega" in r.url else None)
        try:
            await page.goto(FOLDER, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(8000)
            rows = await page.evaluate(
                """() => {
                  const out = [];
                  const cand = document.querySelectorAll(
                    'tr[data-item], [class~="data-item"], .fm-row');
                  for (const el of cand) {
                    const nm = el.querySelector('[class~="name"], .file-name');
                    const sz = el.querySelector('[class~="size"]');
                    const txt = nm ? nm.textContent : '';
                    if (txt) out.push({tag: el.tagName, cls: el.className.slice(0, 60),
                                       name: txt.trim().slice(0, 70),
                                       size: sz ? sz.textContent.trim() : ''});
                  }
                  return out.slice(0, 20);
                }""")
            print(f"行数 {len(rows)}，前 12 行:")
            for r in rows[:12]:
                print(f"   <{r['tag']} class={r['cls']!r}> {r['name']!r} size={r['size']!r}")
            targets = [r for r in rows if r["name"].endswith(".funscript")]
            targets.sort(key=lambda r: parse_size(r["size"]) or 10 ** 9)
            if not targets:
                print("!! 没找到 funscript 行，放弃点击实验")
                return
            tgt = targets[0]
            print(f"\n点击目标（最小 funscript）: {tgt['name']!r} {tgt['size']!r}")

            # 右键该行 -> 扒右键菜单
            row_loc = page.get_by_text(tgt["name"], exact=True).first
            await row_loc.click(button="right")
            await page.wait_for_timeout(1500)
            items = await page.evaluate(
                """() => Array.from(document.querySelectorAll(
                     '[role="menuitem"], .context-menu-item, .dropdown-item'))
                   .map(e => e.textContent.trim()).filter(Boolean).slice(0, 15)""")
            print(f"右键菜单项: {items}")
            dl_item = page.get_by_role("menuitem", name=re.compile(r"下载|download", re.I))
            n = await dl_item.count()
            print(f"菜单里含 下载/download 的项 {n} 个")

            print("\n等下载事件（最长 150s）...")
            try:
                async with page.expect_download(timeout=150000) as dl_info:
                    if n:
                        await dl_item.first.click()
                    else:
                        # 兜底：左键选中行再点工具栏"下载"
                        await row_loc.click()
                        await page.wait_for_timeout(800)
                        await page.get_by_role("button", name="下载").first.click()
                dl = await dl_info.value
                print(f"下载事件 OK: suggested={dl.suggested_filename!r}")
                print(f"userstorage 请求 {len(storage_hits)} 个")
                await dl.cancel()
                print("已 cancel")
            except Exception as e:
                print(f"下载事件失败: {e}")
                print(f"userstorage 请求 {len(storage_hits)} 个")
                for u in storage_hits[:5]:
                    print(f"   {u}")
        finally:
            await page.close()

        # ---- 2) file 页：只扒下载按钮结构 ----
        page = await engine.context.new_page()
        try:
            await page.goto(FILEPG, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(10000)
            btns = await page.evaluate(
                """() => Array.from(document.querySelectorAll(
                     '[class~="download"], button, a[class]'))
                   .filter(e => /download|下载/i.test(
                     (e.className + ' ' + e.textContent).slice(0, 200)))
                   .map(e => ({tag: e.tagName,
                               cls: String(e.className).slice(0, 80),
                               html: e.outerHTML.slice(0, 220)}))
                   .slice(0, 8)""")
            print(f"\nfile 页下载相关元素 {len(btns)} 个:")
            for b in btns:
                print(f"   <{b['tag']} class={b['cls']!r}>")
                print(f"      {squeeze(b['html'], 220)}")
        finally:
            await page.close()
        print("\n完成，3s 后关浏览器")
        await asyncio.sleep(3)


asyncio.run(main())
