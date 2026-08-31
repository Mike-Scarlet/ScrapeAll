
import argparse, asyncio, json, logging, os, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_general_lib.environment_setup.logging_setup import *
logging.basicConfig(
  level=logging.NOTSET if os.environ.get("DL_DEBUG") else logging.INFO,
  format="[%(asctime)s] %(message)s",
)

from scrape_all.downloader.adapters import adapter_for
from scrape_all.downloader.engine import DownloadEngine
from config import DOWNLOADER_CONCURRENCY, DOWNLOADER_PROXY_SERVER

# 下载基建的真链接验证：从 eroscripts.db 挑库里的真实链接，probe + 小文件试下载。
# 只动 data/eroscripts/files/_verify/，不碰 topic stat、不建任务表（编排层的事）。
#
#   python scripts/probe_downloader.py --host catbox                 # 只探活
#   python scripts/probe_downloader.py --host catbox --download      # 探活+试下载
#   python scripts/probe_downloader.py --host eros --download --limit 5
#   python scripts/probe_downloader.py --url https://files.catbox.moe/xxx.mp4
#
#   --host eros 需要 discourse 登录态（browser_session/ profile，没有会挂住等人工）

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "data", "eroscripts.db")
_VERIFY_DIR = os.path.join(_ROOT, "data", "eroscripts", "files", "_verify")
MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024   # 验证下载的单文件上限，防一条巨物误伤


def pick_links(host: str, limit: int) -> list[str]:
  """从库里按 host 挑真实链接（去重、稳定序），也顺带撞死链样本"""
  con = sqlite3.connect(_DB)
  try:
    rows = con.execute(
        "SELECT links_json FROM EroTopicItem WHERE stat=2 AND links_json IS NOT NULL"
    ).fetchall()
  finally:
    con.close()
  keys = {
      "catbox": "catbox.moe",
      "eros": "discuss.eroscripts.com/uploads/",
      "pixeldrain": "pixeldrain.com",
      "gofile": "gofile.io/d/",
    "mega": "mega.nz/",
    "hanime": "hanime1.me/watch",   # /download?v= 形态用 --url 指定
    "rule34": "rule34video.com/video/",
    "hmvmania": "hmvmania.com/video/",
  }
  key = keys[host]
  seen, out = set(), []
  for (lj,) in rows:
    for l in json.loads(lj):
      url = l["url"]
      if url in seen:
        continue
      if key in url:
        seen.add(url); out.append(url)
    if len(out) >= limit:
      break
  return out[:limit]


def fmt_size(n):
  return f"{n / 1024 / 1024:.1f}MB" if n and n >= 1024 * 1024 else f"{n}B" if n else "?"


async def verify(urls: list[str], do_download: bool, stealth: bool = False):
  os.makedirs(_VERIFY_DIR, exist_ok=True)
  results = []
  async with DownloadEngine(DOWNLOADER_PROXY_SERVER, DOWNLOADER_CONCURRENCY,
                            stealth=stealth) as engine:
    if any("discuss.eroscripts.com" in u for u in urls):
      from scrape_all.sites.eroscripts.login import ErosLogin
      await ErosLogin.GuaranteeErosLogin(engine.context)

    for i, url in enumerate(urls, 1):
      adapter = adapter_for(url)
      if adapter is None:
        print(f"[{i}/{len(urls)}] {url}\n    无 adapter，跳过")
        continue
      try:
        probe = await adapter.probe(engine, url)
        line = (f"[{i}/{len(urls)}] probe={probe.status} "
                f"size={fmt_size(probe.size)} name={probe.filename} "
                f"{'files=%d ' % len(probe.files) if probe.files else ''}{probe.note}")
        dl_status = ""
        if do_download and probe.status == "alive" \
            and (probe.size is None or probe.size <= MAX_DOWNLOAD_SIZE):
          dl = await adapter.download(engine, url, _VERIFY_DIR)
          dl_status = f" | download={dl.status} {fmt_size(dl.size)} {dl.note or ''}"
          results.append((url, probe.status, dl.status))
        else:
          results.append((url, probe.status, None))
        print(f"{line}{dl_status}\n    {url}")
      except Exception as e:
        results.append((url, "error", None))
        print(f"[{i}/{len(urls)}] 异常: {e}\n    {url}")

  print("\n=== 汇总 ===")
  from collections import Counter
  probes = Counter(r[1] for r in results)
  dls = Counter(r[2] for r in results if r[2])
  print(f"probe: {dict(probes)}  download: {dict(dls) or '未开启'}")


async def main():
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description="下载基建真链接验证")
  ap.add_argument("--host", choices=("catbox", "eros", "pixeldrain", "gofile", "mega", "hanime", "rule34", "hmvmania"),
                  help="从库里挑该 host 的链接")
  ap.add_argument("--url", action="append", help="直接指定链接（可多次）")
  ap.add_argument("--limit", type=int, default=3)
  ap.add_argument("--download", action="store_true",
                  help=f"探活为 alive 且 <= {MAX_DOWNLOAD_SIZE // 1024 // 1024}MB 的试下载")
  ap.add_argument("--stealth", action="store_true",
                  help="patchright 会话（间歇吃 CF 挑战的流媒体源站用）")
  args = ap.parse_args()

  urls = args.url or []
  if args.host:
    urls += pick_links(args.host, args.limit)
  if not urls:
    ap.error("--host 或 --url 至少给一个")
  await verify(urls, args.download, stealth=args.stealth)
  try:
    input("\npress enter to exit ")
  except EOFError:
    pass


asyncio.run(main())
