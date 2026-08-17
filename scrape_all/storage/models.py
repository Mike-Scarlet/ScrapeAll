
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
    5 = deferred    解析跑过但结构超规（如无合集卡）：挂起，规则补全后重试
    -1 = fetch 失败   -2 = parse 失败
  """
  url: str = Field(primary_key=True)
  title: str = Field(not_null=True)
  post_time: str = Field(not_null=True)     # 时间戳归一化为 UTC ISO 文本，解析不了存原文
  stat: int = Field(not_null=True, default=0)
  links_json: str = Field(not_null=True, default="")   # 解析后链接清单 json：[{name, url, pwd, unzip_pwd, pan_type, box_title, card_title, source, date}]
  first_seen: float = Field(not_null=True)
  last_seen: float = Field(not_null=True)


@PySQLModel(initialize_fields=True)
class ScrapeMeta:
  """抓取元信息 kv（history_done 回填完成标志等）"""
  key: str = Field(primary_key=True)
  value: str = Field(not_null=True)


@PySQLModel(initialize_fields=True)
class LibraryFolder:
  """local_library：NAS 已确认库（erodouga/creators/[4]confirmed）的作者文件夹镜像

  folder_key = f"{uploader}:{creator}"（如 "yejiang:AS109"）。
  搬运到 <root>\\[yejiang]\\<creator>\\ 后文件夹名不再带日期，"上一次fetch最后时间"
  由 folder_date 在库里持续维护（初始值取自搬运前文件夹名的 {YY.MM} 标记）。
  月份等以后要加的信息放 content_json，免 migrate。
  """
  folder_key: str = Field(primary_key=True)
  creator: str = Field(not_null=True)
  uploader: str = Field(not_null=True)
  original_name: str = Field(not_null=True)    # 搬运前原文，如 "AS109 {25.11} [yejiang]"
  rel_path: str = Field(not_null=True)         # 相对库根当前路径，统一存 "/"；搬运后 "yejiang/AS109"
  folder_date: str = Field(not_null=True)      # 归一化 "2025.11"（仅年份标记为 "2022"）
  parse_method: str = Field(not_null=True)     # 结构枚举：month_flat/year_nested/loose_files/mixed
  content_json: str = Field(not_null=True, default="")  # {"downloaded_months": {"2024.12": ["2024/24.12 x", ...]}} 月份->夹内索引路径
  first_seen: float = Field(not_null=True)
  last_seen: float = Field(not_null=True)
