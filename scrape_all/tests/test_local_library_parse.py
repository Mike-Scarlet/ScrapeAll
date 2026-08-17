

from scrape_all.local_library.consts import ParseMethod
from scrape_all.local_library.parse import (
  Entry, classify_folder, month_of, normalize_marker, parse_top_name,
)


# ---- 顶层文件夹名：作者名 {YY.MM} [上传者] ----

def test_parse_top_name_normal():
  fn = parse_top_name("AS109 {25.11} [yejiang]")
  assert (fn.creator, fn.folder_date, fn.uploader) == ("AS109", "2025.11", "yejiang")
  fn = parse_top_name("3Dimm Animation {24.12} [Krenio]")
  assert (fn.creator, fn.folder_date, fn.uploader) == ("3Dimm Animation", "2024.12", "Krenio")
  # 日文名作者 / 含空格
  fn = parse_top_name("白麦鱼 {25.10} [yejiang]")
  assert fn.creator == "白麦鱼" and fn.folder_date == "2025.10"


def test_parse_top_name_year_only_and_mismatch():
  # {YY} 仅年份容错（现存非 yejiang 夹的真实写法）
  fn = parse_top_name("Pangxxx {22} [blyat]")
  assert fn is not None and fn.folder_date == "2022"
  # 非规范命名一律 None（真实脏样本）
  assert parse_top_name("dd_dd") is None
  assert parse_top_name("KemKem[xushi]") is None
  assert parse_top_name("セネト {24.12} {funscript added}") is None
  assert parse_top_name("Eros (+SD) ~2025-10 [场景卡] [40G][c291dGhwbHVz]") is None
  assert parse_top_name("貧乳愛好会 (貧乳愛好会会長補佐代理見習い) [hihihiha]") is None
  # 月份越界
  assert parse_top_name("X {25.99} [yejiang]") is None
  assert normalize_marker("25.11") == "2025.11"
  assert normalize_marker("22") == "2022"
  assert normalize_marker("25.99") is None


# ---- 月份 token：YY.MM / YYYY-MM / 带日 / 带描述 ----

def test_month_of_variants():
  assert month_of("25.01 水兰儿 vip房①") == "2025.01"
  assert month_of("24.12 水兰儿 vip房①") == "2024.12"
  assert month_of("23.01.03 纳西妲 1") == "2023.01"      # 日期文件夹取年月
  assert month_of("2025-01") == "2025.01"                # 四位年份 + 横线
  assert month_of("2025-6") == "2025.06"                 # 月份不补零
  assert month_of("18.06") == "2018.06"                  # 裸月份夹
  assert month_of("23.03 津岛善子_23.03 津岛善子.mp4") == "2023.03"   # 散文件
  assert month_of("2025.10") == "2025.10"
  # 4 位年：日段后允许任意非数字字符直接跟（xssxsxk 真实样本）
  assert month_of("2025.5.25【万由里 4】DATE・A・LIVE") == "2025.05"
  assert month_of("2025.7.15【能美クドリャフカ 能美库特莉亚芙卡】Little Busters!") == "2025.07"
  # 2 位年：尾点+空格写法（kiriyuki 真实样本）
  assert month_of("23.12. 妮可") == "2023.12"
  assert month_of("23.12. 妮可.mp4") == "2023.12"


def test_month_of_negatives():
  assert month_of("1.主系列") is None          # 一位数 + 非数字"月"
  assert month_of("10 梅比乌斯") is None        # 数字后无分隔符
  assert month_of("2023") is None              # 纯年份不是月份 token
  assert month_of("卡芙卡") is None
  assert month_of("13.99 xxx") is None         # 月份越界
  assert month_of("25.0") is None
  # 2 位年的垃圾形态（xssxsxk/kisaki 真实样本）：页码图 / 集数 / 版本号
  assert month_of("22.1.jpg") is None
  assert month_of("10.2-test.mp4") is None
  assert month_of("67.5.朱鸢.mp4") is None
  assert month_of("19.06.02a") is None


# ---- 结构分类（lister 注入假树） ----

def make_lister(tree: dict) -> "callable":
  return lambda rel: tree.get(rel, [])   # 未在假树里列出的目录视为空目录


def test_classify_month_flat():
  top = [Entry("24.12 水兰儿 vip房①", True), Entry("25.01 水兰儿 vip房②", True)]
  r = classify_folder(top, make_lister({}))
  assert r.ok and r.parse_method == ParseMethod.MONTH_FLAT
  assert r.months == ["2024.12", "2025.01"]
  assert r.month_index == {"2024.12": ["24.12 水兰儿 vip房①"],
                           "2025.01": ["25.01 水兰儿 vip房②"]}


def test_classify_year_nested_with_day_folders_and_stray_file():
  # Chr 形态：年份夹里是 "23.01.03 纳西妲" 按日命名的作品夹 + 散文件容忍
  top = [Entry("2023", True), Entry("2024", True)]
  inner = {
      "2023": [Entry("23.01.03 纳西妲 1", True), Entry("23.04.04 纳西妲 2", True)],
      "2024": [Entry("24.02.05 纳西妲 9", True), Entry("cover.jpg", False)],
  }
  r = classify_folder(top, make_lister(inner))
  assert r.ok and r.parse_method == ParseMethod.YEAR_NESTED
  assert r.months == ["2023.01", "2023.04", "2024.02"]
  assert r.month_index == {
      "2023.01": ["2023/23.01.03 纳西妲 1"],
      "2023.04": ["2023/23.04.04 纳西妲 2"],
      "2024.02": ["2024/24.02.05 纳西妲 9"],
  }
  assert any("cover.jpg" in w for w in r.reasons)   # 散文件只提示不判死


def test_classify_loose_files():
  top = [Entry("23.03 津岛善子_23.03 津岛善子.mp4", False),
         Entry("23.05 岚千砂都_23.05 岚千砂都 1.mp4", False)]
  r = classify_folder(top, make_lister({}))
  assert r.ok and r.parse_method == ParseMethod.LOOSE_FILES
  assert r.months == ["2023.03", "2023.05"]
  assert r.month_index == {"2023.03": ["23.03 津岛善子_23.03 津岛善子.mp4"],
                           "2023.05": ["23.05 岚千砂都_23.05 岚千砂都 1.mp4"]}


def test_classify_mixed_year_and_month():
  # 咕嘿嘿/xssxsxk 形态：年份夹与直接月份夹并存（横线写法）
  top = [Entry("2024", True), Entry("2025-01", True), Entry("2025-6", True)]
  inner = {"2024": [Entry("24.03 xxx", True)]}
  r = classify_folder(top, make_lister(inner))
  assert r.ok and r.parse_method == ParseMethod.MIXED
  assert r.months == ["2024.03", "2025.01", "2025.06"]
  assert r.month_index == {"2024.03": ["2024/24.03 xxx"],
                           "2025.01": ["2025-01"], "2025.06": ["2025-6"]}


def test_classify_collects_months_at_any_depth():
  # xssxsxk 形态：年份夹下只有少量月份夹，但月份夹内部还有日期命名的子夹，
  # 全深度递归收集，漏抓会导致误判"该月未下载"；month_index 同时记录
  # 月份夹本身与内部日期子夹两条索引链（目录树如何索引到该月）
  top = [Entry("2025", True)]
  inner = {
      "2025": [Entry("25.01", True), Entry("25.06", True)],
      "2025/25.01": [Entry("25.01.03 a", True), Entry("25.01.15 b", True)],
      "2025/25.06": [Entry("25.06.02 c", True), Entry("Thumbs.db", False)],
  }
  r = classify_folder(top, make_lister(inner))
  assert r.ok and r.parse_method == ParseMethod.YEAR_NESTED
  assert r.months == ["2025.01", "2025.06"]
  assert r.month_index == {
      "2025.01": ["2025/25.01", "2025/25.01/25.01.03 a", "2025/25.01/25.01.15 b"],
      "2025.06": ["2025/25.06", "2025/25.06/25.06.02 c"],
  }


def test_classify_out_of_scope_shapes():
  # 顶层系列夹（dlaldn 形态）
  r = classify_folder([Entry("1.主系列", True), Entry("2副系列", True)], make_lister({}))
  assert not r.ok and any("1.主系列" in x for x in r.reasons)
  # 角色名夹（kisaki 形态）
  r = classify_folder([Entry("卡芙卡", True), Entry("25.01 x", True)], make_lister({}))
  assert not r.ok
  # 年份夹内出现非日期目录：结构不确定
  r = classify_folder([Entry("2024", True)],
                      make_lister({"2024": [Entry("原神", True)]}))
  assert not r.ok and any("原神" in x for x in r.reasons)
  # 顶层裸文件不带日期
  r = classify_folder([Entry("说明.txt", False)], make_lister({}))
  assert not r.ok
  # 空文件夹
  assert not classify_folder([], make_lister({})).ok
