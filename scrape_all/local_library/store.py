

# local_library 落库：LibraryFolder 表的 upsert 与查询。
# first_seen 首见后不动，last_seen 每次扫描刷新（沿用 PostStore 的约定）。

import json
import time
from typing import Optional, Sequence

from python_general_lib.database.sqlite3_wrap.multiple_models_sqlite_database import \
    MultipleModelsSQLiteDatabase

from scrape_all.storage.models import LibraryFolder


class LibraryStore:
  """NAS 库状态镜像的落库读写"""

  def __init__(self, db_path: str):
    self.db = MultipleModelsSQLiteDatabase(db_path, [LibraryFolder])
    self.db.Initiate()

  def __enter__(self) -> "LibraryStore":
    return self

  def __exit__(self, exc_type, exc, tb):
    self.close()

  def get(self, folder_key: str) -> Optional[LibraryFolder]:
    return self.db.QueryOne(LibraryFolder, where="folder_key = ?", params=(folder_key,))

  def all_folders(self) -> list[LibraryFolder]:
    return self.db.QueryRecords(LibraryFolder)

  def upsert_folder(self, folder_key: str, creator: str, uploader: str,
                    original_name: str, rel_path: str, folder_date: str,
                    parse_method: str, months: Sequence[str],
                    now: Optional[float] = None) -> str:
    """写入/刷新一条镜像记录，返回 "new" / "updated"。

    folder_date 等字段一律按传入值写：未搬运时 scan 传文件夹名解析出的日期
    （搬运前手工改名会跟上来）；已搬运后文件夹名无日期，scan 传回库内原值。
    """
    if now is None:
      now = time.time()
    content = json.dumps({"downloaded_months": list(months)}, ensure_ascii=False)
    row = self.get(folder_key)
    if row is None:
      self.db.InsertRecord(LibraryFolder(
          folder_key=folder_key, creator=creator, uploader=uploader,
          original_name=original_name, rel_path=rel_path, folder_date=folder_date,
          parse_method=parse_method, content_json=content,
          first_seen=now, last_seen=now))
      self.db.Commit()
      return "new"
    item = LibraryFolder(folder_key=folder_key)
    item.original_name = original_name
    item.rel_path = rel_path
    item.folder_date = folder_date
    item.parse_method = parse_method
    item.content_json = content
    item.last_seen = now
    self.db.RecordFieldChanged(item, [
        "original_name", "rel_path", "folder_date", "parse_method",
        "content_json", "last_seen"])
    self.db.Commit()
    return "updated"

  def update_rel_path(self, folder_key: str, rel_path: str,
                      now: Optional[float] = None):
    """搬运成功后更新位置；其余字段不动"""
    if now is None:
      now = time.time()
    item = LibraryFolder(folder_key=folder_key, rel_path=rel_path, last_seen=now)
    self.db.RecordFieldChanged(item, ["rel_path", "last_seen"])
    self.db.Commit()

  def close(self):
    self.db.Close()
