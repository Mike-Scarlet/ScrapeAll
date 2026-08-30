# 泛化验证（只读）：再抽 2 条 /d 形态的 dead 链接 + 唯一 1 条 /u 形态 dead，
# 看同 id 的 /d 与 /u 各返回什么 —— 模式是否全库成立
import os
import re
import sys
import asyncio
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from config import DOWNLOADER_PROXY_SERVER
from scrape_all.downloader.engine import DownloadEngine
from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
DB = os.path.join(DB, "data", "eroscripts.db")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def form_of(url):
    m = re.match(r"^/(u|d|l|api/file|api/list)/", urlsplit(url).path)
    return m.group(1) if m else "?"


def swap(url, to):
    p = urlsplit(url)
    path = re.sub(r"^/(u|d|l|api/file|api/list)/", f"/{to}/", p.path)
    return f"{p.scheme}://{p.netloc}{path}"


with TopicStore(DB) as store:
    rows = store.db.QueryRecords(EroLink, where="host = ?", params=["pixeldrain.com"])
dead_d = [r.url for r in rows if r.probe_status == "dead" and form_of(r.url) == "d"][:2]
dead_u = [r.url for r in rows if r.probe_status == "dead" and form_of(r.url) == "u"][:1]
targets = dead_d + dead_u
print("抽查样本:")
for u in targets:
    print(f"  {u}")


async def main():
    async with DownloadEngine(DOWNLOADER_PROXY_SERVER) as engine:
        print("\n同 id 双形态（Range 探头）：")
        for u in targets:
            for form in ("u", "d"):
                alt = swap(u, form)
                r = await engine.probe_headers(alt, park_url="https://pixeldrain.com/")
                print(f"  {alt}  -> {r['status']}")

asyncio.run(main())
