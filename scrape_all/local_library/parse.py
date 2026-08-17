

# local_library 解析纯逻辑：NAS 文件夹名与内部结构的日期提取、结构分类。
# 不做任何 IO（目录列表由调用方通过 lister 注入），可独立单测。
#
# 现实格式（实测 [4]confirmed 下 49 个 yejiang 夹归纳）：
#   顶层名   "作者名 {YY.MM} [上传者]"（个别非 yejiang 的只有 {YY} 年份）
#   月份 token（文件夹/文件名前缀，分隔符 . 或 -）：
#     "25.01 水兰儿 vip房①"  "23.01.03 纳西妲 1"（带日）  "2025-01"  "2025-6"
#   年份文件夹 "^\\d{4}$"，内层再挂月份/日期文件夹

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from scrape_all.local_library.consts import ParseMethod

# 顶层文件夹名：作者名 {YY.MM 或 YY} [上传者]
TOP_NAME_RE = re.compile(
    r"^(?P<creator>.+?) \{(?P<marker>\d{2}(?:\.\d{2})?)\} \[(?P<uploader>[^\]]+)\]$")
# 月份 token：开头 YY.MM / YYYY-MM，可跟 ".DD" 日与描述。按年份位数区别对待
# 尾部（实测库里的真实样本归纳，放宽过度会把页码图/集数当月份收进来）：
#   4 位年（歧义小）：日段后允许任意非数字字符直接跟，如 "2025.5.25【万由里 4】"
#   2 位年（页码 "22.1.jpg"、集数 "67.5.朱鸢.mp4" 长这样）：只允许 空格/下划线/结束，
#     外加 "23.12. 妮可" 这种尾点+空格的写法
MONTH_TOKEN_RE = re.compile(
    r"^(?:(?P<y4>\d{4})[.\-](?P<m>\d{1,2})(?:[.\-]\d{1,2})*(?:[\s_].*|\D.*)?"
    r"|(?P<y2>\d{2})[.\-](?P<m2>\d{1,2})(?:[.\-]\d{1,2})*\.?(?:[\s_].*)?)$")
# 纯年份文件夹（year_nested 的顶层）
YEAR_DIR_RE = re.compile(r"^\d{4}$")


@dataclass
class Entry:
  """一层目录里的一个条目（不区分排序，is_dir 决定分类走向）"""
  name: str
  is_dir: bool


@dataclass
class FolderName:
  """顶层文件夹名的解析结果"""
  creator: str
  folder_date: str        # 归一化："25.11"->"2025.11"，"22"->"2022"
  uploader: str


@dataclass
class FolderScan:
  """一个 creator 文件夹内部结构的解析结果"""
  ok: bool
  parse_method: str = ""
  months: list[str] = field(default_factory=list)   # 归一化月份，已排序（month_index 的 keys）
  month_index: dict[str, list[str]] = field(default_factory=dict)
  # 月份 -> creator 夹内相对路径（"/" 分隔，已排序）：该月被目录树索引到的每一条
  # （月份夹本身与其内部日期子夹/散文件都是独立索引链）；rel_path + 路径 = 库根全路径
  reasons: list[str] = field(default_factory=list)  # 工况外原因；ok=True 时为提示性 warning


def normalize_marker(marker: str) -> Optional[str]:
  """顶层名 {YY.MM}/{YY} 标记 -> "YYYY.MM"/"YYYY"；月份越界返回 None"""
  y, _, m = marker.partition(".")
  yyyy = 2000 + int(y)     # 现存库全是 20xx
  if m:
    if not 1 <= int(m) <= 12:
      return None
    return f"{yyyy}.{int(m):02d}"
  return str(yyyy)


def parse_top_name(name: str) -> Optional[FolderName]:
  """解析顶层文件夹名；不符合规范（无花括号/无上传者/日期越界）返回 None"""
  m = TOP_NAME_RE.match(name)
  if not m:
    return None
  date = normalize_marker(m.group("marker"))
  if date is None:
    return None
  return FolderName(creator=m.group("creator"), folder_date=date,
                    uploader=m.group("uploader"))


def month_of(name: str) -> Optional[str]:
  """条目名 -> 归一化月份 "YYYY.MM"；不是日期 token 返回 None（纯年份也返回 None）"""
  m = MONTH_TOKEN_RE.match(name)
  if not m:
    return None
  y = m.group("y4") or m.group("y2")
  mo = int(m.group("m") or m.group("m2"))
  if not 1 <= mo <= 12:
    return None
  yyyy = int(y) if len(y) == 4 else 2000 + int(y)
  return f"{yyyy}.{mo:02d}"


def classify_folder(top: list[Entry],
                    lister: Callable[[str], list[Entry]]) -> FolderScan:
  """判定 creator 文件夹的内部结构并收集月份。

  规则（"彻底可解析"的判定）：
    - 顶层：每个条目必须是 年份文件夹 / 月份token文件夹 / 带日期前缀的散文件，
      有一个覆盖不了 -> 整夹工况外（系列结构如 "1.主系列" 就死在这里）
    - 年份夹内层：目录必须全是日期 token；散文件容忍——不判工况外
  月份收集在判 ok 的结构内全深度递归（月份夹内部还有日期命名的子夹，
  如 xssxsxk/2025/25.01/25.01.03 xx，漏抓会误判"该月未下载"）；每条月份
  token 同时记录其所在相对路径（month_index），供审计误判与追溯来源。
  lister(相对路径，"/" 分隔) 返回该子夹的一层条目，供测试注入假树。
  """
  if not top:
    return FolderScan(False, reasons=["顶层为空"])

  bad: list[str] = []
  year_dirs: list[str] = []
  has_month_dir = False
  has_dated_file = False

  for e in top:
    mo = month_of(e.name)
    if not e.is_dir:
      if mo:
        has_dated_file = True
      else:
        bad.append(e.name)
    elif YEAR_DIR_RE.match(e.name):
      year_dirs.append(e.name)
    elif mo:
      has_month_dir = True
    else:
      bad.append(e.name)
  if bad:
    return FolderScan(False, reasons=[f"顶层条目无法归类: {n}" for n in bad])

  warnings: list[str] = []
  for yd in year_dirs:
    for e in lister(yd):
      if not e.is_dir and month_of(e.name) is None:
        warnings.append(f"年份夹 {yd} 内未计月份的散文件: {e.name}")
      elif e.is_dir and month_of(e.name) is None:
        # 年份夹里出现非日期目录 = 结构不确定（可能是系列细分），整夹工况外
        return FolderScan(False, reasons=[f"年份夹 {yd} 内非日期目录: {e.name}"])

  index: dict[str, set[str]] = {}

  def collect(entries: list[Entry], rel: str):
    for e in entries:
      mo = month_of(e.name)
      path = f"{rel}/{e.name}" if rel else e.name
      if mo:
        index.setdefault(mo, set()).add(path)
      if e.is_dir:
        collect(lister(path), path)

  collect(top, "")
  if not index:
    return FolderScan(False, reasons=["判 ok 但一个月份都没抓到（规则漏洞，请人工看）"])

  if year_dirs and (has_month_dir or has_dated_file):
    method = ParseMethod.MIXED
  elif year_dirs:
    method = ParseMethod.YEAR_NESTED
  elif has_month_dir:
    method = ParseMethod.MONTH_FLAT
  else:
    method = ParseMethod.LOOSE_FILES
  month_index = {mo: sorted(paths) for mo, paths in index.items()}
  return FolderScan(True, method, sorted(month_index), month_index, warnings)
