
from python_general_lib.database.sqlite3_wrap import *

@PySQLModel(initialize_fields=True)
class PostItem:
  title: str = Field(not_null=True)
  url: str = Field(not_null=True)
  process_stat: int = Field(not_null=True)
  retrive_time: float = Field(not_null=True)
  use_shared_link: str = Field(not_null=True)
  shared_link_collect: str = Field(not_null=True)   # json
