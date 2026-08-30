
import hashlib
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


def url_token(url: str, length: int = 8) -> str:
  """URL -> 稳定短 token（hex）。同帖不同链接解析出同一落盘名时（镜像真名/
  同系列撞名/检查名与 suggested 名不同源），拿它区分出第二把。"""
  digest = hashlib.blake2b(url.encode("utf-8"), digest_size=4).hexdigest()
  return digest[:length]


def resolve_save_path(dest_dir: str, name: str, token: str) -> str:
  """撞名安全的落盘路径：name 没被占 -> name；被占 -> {stem}.{token}{ext}。
  token 名也被占时照样返回 token 名——同 URL 重跑即同内容，覆盖无害；
  不同内容互撞永远不覆盖已有文件（防的是静默丢内容，324422 实案）。"""
  dest = os.path.join(dest_dir, name)
  if not os.path.exists(dest):
    return dest
  stem, ext = os.path.splitext(name)
  return os.path.join(dest_dir, f"{stem}.{token}{ext}")


def same_size_or_unknown(path: str, expected: int | None,
                         rel_tol: float = 0.0) -> bool:
  """已存在文件是否就是这条链接的内容（镜像）：体积对得上（或未知体积时
  保守认是）。前置幂等跳过用；体积对不上的"已存在"是不同内容撞名，
  该让引擎落 {stem}.{token}{ext} 第二把，不能吃掉新内容。
  rel_tol：expected 来自页面人读文本（"39.5MB"）时给相对容差（mega/pixeldrain/
  gofile 建议 0.03，zip 整包估和建议 0.1）；来自响应头精确字节的保持 0。"""
  if not expected:
    return True
  try:
    actual = os.path.getsize(path)
  except OSError:
    return False
  if actual == expected:
    return True
  return rel_tol > 0 and abs(actual - expected) <= rel_tol * max(actual, expected)
