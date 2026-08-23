
import os
import re

# 落盘路径工具。Windows 文件系统约束为主（本机与 NAS 都是 NTFS/SMB）：
#   - <>:"/\|?* 与控制字符非法 -> 替换为 _（替换不跳过，保留可读性）
#   - 结尾的空格/点会被 Win32 静默剥掉 -> 主动剥
#   - 设备保留名（CON/PRN/AUX/NUL/COM1-9/LPT1-9，带扩展名也一样病）-> 前缀 _
#   - 超长截断时保住扩展名
_ILLEGAL_CHARS = '<>:"/\\|?*'
_RESERVED_NAMES = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_MAX_EXT_LEN = 16   # 正常扩展名远短于此；超长的多半是把查询串切进了名字


def sanitize_filename(name: str, max_len: int = 120) -> str:
  """任意字符串 -> 可安全当 Windows 文件名的字符串（空/全非法 -> unnamed）"""
  if not name:
    return "unnamed"
  cleaned = re.sub(r"\s+", " ", name)   # \t\n 先折成空格，别走控制字符替换变 _
  cleaned = "".join("_" if (c in _ILLEGAL_CHARS or ord(c) < 32) else c for c in cleaned)
  cleaned = cleaned.strip(" .")
  if not cleaned or cleaned.strip("_") == "":
    return "unnamed"

  stem, ext = os.path.splitext(cleaned)
  if len(ext) > _MAX_EXT_LEN:           # 扩展名本身超长：当正文处理，不保
    stem, ext = cleaned, ""
  if stem.upper() in _RESERVED_NAMES:   # "CON.funscript" 在 Win32 一样建不出来
    stem = "_" + stem
  if len(stem) + len(ext) > max_len:
    stem = stem[:max_len - len(ext)].rstrip(" .")
  return stem + ext or "unnamed"


def topic_dir_name(topic_id: int, title: str, max_len: int = 80) -> str:
  """topic 级落盘目录名：{topic_id}_{标题 slug}。id 打头保证唯一，标题截断保可读"""
  slug = sanitize_filename(title, max_len=max_len)
  return f"{topic_id}_{slug}"
