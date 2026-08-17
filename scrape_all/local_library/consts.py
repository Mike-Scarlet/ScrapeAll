

class ParseMethod:
  """creator 文件夹内部结构枚举（LibraryFolder.parse_method 的取值）

  每种都要求全部条目被日期规则覆盖，才算"彻底可解析"；覆盖不了的
  （系列/角色命名的，如 dlaldn、kisaki）是工况外，不入库、不搬运。
  """
  MONTH_FLAT = "month_flat"      # 顶层全是月份 token 文件夹（含 "2025-01" 横线变体）
  YEAR_NESTED = "year_nested"    # 顶层全是年份文件夹，内层目录全是日期 token
  LOOSE_FILES = "loose_files"    # 顶层无子文件夹，散文件全部带日期前缀
  MIXED = "mixed"                # 顶层年份夹与直接月份夹并存，但条目全被规则覆盖
