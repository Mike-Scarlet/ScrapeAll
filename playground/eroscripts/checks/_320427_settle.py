# 落库：320427 坏件置换复位——EroLink dl_size/dl_at/note 更新（failed 的 EroExtract
# 行不删，extract 管线会把 failed 行重试，解压成功 OR REPLACE 成 done）
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrape_all.sites.eroscripts.store import TopicStore
from scrape_all.storage.models import EroLink

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEST = r"J:\es_scrape"
URL = "https://mega.nz/folder/u0clyADK#JtMiAhz1YblucezTsXjR_A"
REL = "320427/【KK VR180】2000フォロワー感謝 長風 长风 Changfeng 8K60FPS.zip"

actual = os.path.getsize(os.path.join(DEST, *REL.split("/")))
print(f"盘上实际 {actual:,}B")
with TopicStore(os.path.join(ROOT, "data", "eroscripts.db")) as store:
  store.set_link_status(URL, "downloaded", path=REL.replace("/", os.sep), size=actual,
                        note="人工重下复位：下载流串包坏件置换（本地头=别帖内容、中央目录才是自己），"
                             "新件校验本地头=中央目录、单 mp4 1,847,950,221B 与坏件声称体积一致")
  row = store.db.QueryOne(EroLink, where="url = ?", params=(URL,))
  print(f"复核: dl_status={row.dl_status}  dl_size={row.dl_size:,}  dl_at={row.dl_at}")
  print(f"       note={row.dl_note}")
