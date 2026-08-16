
from python_general_lib.database.sqlite3_wrap import Field, PySQLModel


@PySQLModel(initialize_fields=True)
class PostItem:
  """cangku 帖子记录，url 主键去重

  stat 生命周期（帖子被作者更新 -> 时间戳变新 -> 重置为 0 重走全程）：
    0 = discovered  已发现（仅列表 meta：url/标题/时间戳）
    1 = fetched     帖子页已抓取保存
    2 = parsed      已解析（工况内，links 已写入）
    3 = consumed    解析结果已交后续流程处理（终态）
    4 = out_of_scope 解析过滤判定工况外（meta-label 无「动画」；终态）
    -1 = fetch 失败   -2 = parse 失败
  """
  url: str = Field(primary_key=True)
  title: str = Field(not_null=True)
  post_time: str = Field(not_null=True)     # 时间戳归一化为 UTC ISO 文本，解析不了存原文
  stat: int = Field(not_null=True, default=0)
  links_json: str = Field(not_null=True, default="")   # 筛选后链接清单 json：[{name, url, pwd, pan_type}]
  first_seen: float = Field(not_null=True)
  last_seen: float = Field(not_null=True)


@PySQLModel(initialize_fields=True)
class ScrapeMeta:
  """抓取元信息 kv（history_done 回填完成标志等）"""
  key: str = Field(primary_key=True)
  value: str = Field(not_null=True)
