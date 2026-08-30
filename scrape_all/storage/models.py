
from python_general_lib.database.sqlite3_wrap import Field, PySQLModel


@PySQLModel(initialize_fields=True)
class PostItem:
  """cangku 帖子记录，url 主键去重

  stat 生命周期（帖子被作者更新 -> 时间戳变新 -> 重置为 0 重走全程）：
    0 = discovered  已发现（仅列表 meta：url/标题/时间戳）
    1 = fetched     帖子页已抓取保存
    2 = parsed      已解析（工况内，links 已写入）
    3 = consumed    解析结果已交后续流程处理（转存成功或增量对比后全已覆盖；终态）
    4 = out_of_scope 解析过滤判定工况外（meta-label 无「动画」；终态）
    5 = deferred    解析跑过但结构超规（如无合集卡）：挂起，规则补全后重试
    6 = share_dead  分享链接已失效（打开即 share invalid；终态，作者更新帖自然重置重试）
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
class EroTopicItem:
  """eroscripts topic 记录（discourse），topic_id 主键去重
  （/t/<slug>/<id> 的 slug 随标题改名会变，不以 url 为键）

  stat 生命周期（topic 被回复顶起 -> bumped_at 变新 -> 重置为 0 重走全程）：
    0 = discovered  已发现（仅列表 meta：url/标题/作者/标签/时间戳）
    1 = fetched     topic 页已抓取保存
    2 = parsed      已解析（工况内，links 已写入）
    3 = consumed    解析结果已交后续流程处理（终态）
    4 = out_of_scope 解析过滤判定工况外（终态）
    5 = deferred    解析跑过但结构超规：挂起，规则补全后重试
    -1 = fetch 失败   -2 = parse 失败
  """
  topic_id: int = Field(primary_key=True)
  url: str = Field(not_null=True)
  title: str = Field(not_null=True)
  author: str = Field(not_null=True, default="")
  created_at: str = Field(not_null=True, default="")   # 归一化 UTC ISO 文本
  bumped_at: str = Field(not_null=True, default="")    # 归一化 UTC ISO 文本，增量比较用
  tags_json: str = Field(not_null=True, default="")    # ["loli", "straight", ...]
  category_id: int = Field(not_null=True, default=0)
  posts_count: int = Field(not_null=True, default=0)
  views: int = Field(not_null=True, default=0)
  stat: int = Field(not_null=True, default=0)
  links_json: str = Field(not_null=True, default="")   # 解析后链接清单 json（后续阶段写入）
  first_seen: float = Field(not_null=True)
  last_seen: float = Field(not_null=True)


@PySQLModel(initialize_fields=True)
class ScrapeMeta:
  """抓取元信息 kv（history_done 回填完成标志等）"""
  key: str = Field(primary_key=True)
  value: str = Field(not_null=True)


@PySQLModel(initialize_fields=True)
class EroLink:
  """eroscripts consume 链接级状态（url 主键去重：同一 URL 跨 topic 共享一行、只下一次）

  两层状态：probe_status 记探活证据，dl_status 记处置结果——topic 级 CONSUMED
  判定只看 dl_status 是否全部终态。非终态只有 pending / failed（failed 且
  retries 未耗尽时可重试；重试上限 1 次，共 2 次尝试，耗尽转 exhausted）。

  dl_status 终态语义：
    downloaded 已落盘 / skipped 明确跳过（source/other 类、paywall、幂等已存在）
    dead 死链 / manual 等人工介入（needs_auth、无 adapter 的 host）
    exhausted 自动流程重试耗尽放弃（与 manual 分开：不预期人看，仅盘点）
  manual / exhausted 经人工渠道（scripts/ero_links.py set）可改任意合法状态，
  改回 pending 会清零 retries 重走自动流程。
  """
  url: str = Field(primary_key=True)
  host: str = Field(not_null=True, default="")
  kind: str = Field(not_null=True, default="")        # script/media/source/other
  probe_status: str = Field(not_null=True, default="pending")
  probe_retries: int = Field(not_null=True, default=0)
  meta_json: str = Field(not_null=True, default="")   # probe 快照：{filename,size,files}
  dl_status: str = Field(not_null=True, default="pending")
  dl_retries: int = Field(not_null=True, default=0)
  dl_path: str = Field(not_null=True, default="")     # 落盘相对路径
  dl_size: int = Field(not_null=True, default=0)
  dl_note: str = Field(not_null=True, default="")
  first_topic_id: int = Field(not_null=True, default=0)  # 首见 topic，溯源
  probe_at: str = Field(not_null=True, default="")    # UTC ISO 文本
  dl_at: str = Field(not_null=True, default="")       # UTC ISO 文本


@PySQLModel(initialize_fields=True)
class EroExtract:
  """eroscripts 下载后处理：档案（zip/rar）解压状态。archive_path 主键
  （相对落盘根，'/' 分隔）。解压目标固定为档案旁的同名子目录 <stem>/，
  包文件本身保留不删（dl_path 引用完整性）。

  status: done 全条目解出并核验（重跑跳过）/ failed 中断或核验缺件（重跑续传）
  depth: 顶层下载包=1；包内嵌套档案=父 depth+1（extract.EXTRACT_DEPTH_MAX 截止）
  parent_path: 嵌套档案的父 archive_path，顶层为空
  files_json: [{"path": 相对根路径, "size": B, "src": 包内原名, "action": wrote|have}]
  —— 配对决策表的 provenance 从这反查（哪个包出的哪个文件）。
  """
  archive_path: str = Field(primary_key=True)
  topic_id: int = Field(not_null=True, default=0)
  status: str = Field(not_null=True, default="pending")
  depth: int = Field(not_null=True, default=1)
  parent_path: str = Field(not_null=True, default="")
  files_json: str = Field(not_null=True, default="")
  note: str = Field(not_null=True, default="")
  extracted_at: str = Field(not_null=True, default="")


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
