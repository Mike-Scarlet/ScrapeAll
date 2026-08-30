# 人工补解：两个加密 rar（密码来自帖文提示，extract 流水线 stdin=DEVNULL
# 喂不进密码）。复用 extract.extract_rar_file 的临时目录+清洗搬入+体积核验
# 全套规则，落库走 store.mark_extract，note 带密码供将来复解。
#   324125/Hella Good hmv.rar                       <- 帖 #2 "Pass: BigDaddyHurts"
#   312412/.../Pixelumo - Imouto H Short Day.rar    <- 帖 #1 "pw: xxxx1234xxxx"
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.sites.eroscripts.extract import UNRAR_EXE, extract_rar_file
from scrape_all.sites.eroscripts.store import TopicStore

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB = os.path.join(ROOT, "data", "eroscripts.db")
DEST = r"J:\es_scrape"

JOBS = [
    ("324125/Hella Good hmv.rar", 324125, 1, "", "BigDaddyHurts",
     "加密 rar 人工补解：密码 BigDaddyHurts（帖 #2 Pass 提示）"),
    ("312412/2605 - Pixelumo/Pixelumo - Imouto H Short Day.rar", 312412, 2,
     "312412/2605 - Pixelumo.zip", "xxxx1234xxxx",
     "加密 rar 人工补解：密码 xxxx1234xxxx（帖 #1 pw 提示）"),
]


def run_rar_with_pwd(pwd):
  def run(args, timeout):
    # extract_rar_file 传的是 [x, -idq, -o+, rar, tmp]；插 -p<pwd> 在开关区
    full = [UNRAR_EXE, args[0], args[1], args[2], f"-p{pwd}", *args[3:]]
    proc = subprocess.run(full, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, timeout=timeout)
    return proc.returncode, proc.stdout or proc.stderr or ""
  return run


with TopicStore(DB) as store:
  for rel, tid, depth, parent, pwd, note in JOBS:
    abs_p = os.path.join(DEST, *rel.split("/"))
    if not os.path.isfile(abs_p):
      print(f"[跳过] {rel}  盘上不存在")
      continue
    try:
      files, wrote = extract_rar_file(abs_p, DEST, run_rar_with_pwd(pwd))
    except Exception as e:
      print(f"[失败] {rel}  {type(e).__name__}: {e}")
      continue
    store.mark_extract(rel, "done", topic_id=tid, depth=depth,
                       parent_path=parent, files=files, note=note)
    print(f"[补解成功] {rel}  {len(files)} 文件  新写 {wrote / 1024 / 1024:.1f}MB")
    for f in files:
      print(f"    {f['action']:5} {f['size']:>12,}B  {f['path']}")
