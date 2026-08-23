
# proxy settings, set to None to disable
CANGKU_PROXY_SERVER = "http://127.0.0.1:20080"
BAIDU_PAN_PROXY_SERVER = None

# cangku scrape
YEJIANG_USER_ID = "309550"
YEJIANG_HISTORY_CUTOFF = "2025-12-01"   # 历史抓取下界（含该时刻）
YEJIANG_PAGE_LIMIT = 100                # 翻页安全上限（正常应先触发时间/空页停止）
# 分类黑名单后门：入口严格（meta-label 无「动画」一律工况外，包括没挂标签的），
# 个别想要的帖按 id 写在这里，parse 跳过分类检查直接走结构解析
CANGKU_FORCE_IDS = (
    "225885",   # 作者漏挂分类，但帖子/下载区正常，人工确认要
)

# eroscripts scrape（discourse，站内 JSON 走 playwright 登录态页内 fetch）
EROS_PROXY_SERVER = None
EROS_TAG_URL = "https://discuss.eroscripts.com/tag/loli/68"
EROS_HISTORY_CUTOFF = "2026-03-01"   # bumped_at 下界（含该时刻）；全量回填 --full-history 会忽略它
EROS_PAGE_LIMIT = 100                # 翻页安全上限（loli 全量实测 60 页，余量充足）
EROS_CATEGORY_ID = 14                # 只要 Scripts 分类（14），其余工况外不抓

# downloader（媒体/脚本文件下载基建，scrape_all/downloader/）
# 全走浏览器页取回（真实指纹 + 持久 profile 登录态），吃同一份本地代理；
# 并发默认 1 串行，adapter 逐家接入（catbox / eros uploads 已就绪）
DOWNLOADER_PROXY_SERVER = "http://127.0.0.1:20080"
DOWNLOADER_CONCURRENCY = 1
DOWNLOADER_FILES_ROOT = "data/eroscripts/files"   # 相对仓库根；topic 级子目录在编排层定

# baidu pan save
BAIDU_SAVE_TARGET_PATH = "/bangumi/2510"

# local library（NAS 已确认库状态镜像，scripts/local_library.py）
LOCAL_LIBRARY_ROOT = r"\\DS220plus\resource_storage\mike_scarlet\erodouga\creators\[4]confirmed"
# 搬运目标子目录（相对 root），搬进去后文件夹名只留作者名。
# 注意带方括号：不匹配顶层命名规范（作者名 {日期} [上传者]），根扫描天然跳过它
LOCAL_LIBRARY_YEJIANG_DIR = "[yejiang]"

BANGUMI_LINKS = [
    "https://pan.baidu.com/s/11MdxeBxy70cGuBcBmkGoow?pwd=4bs4",
    "https://pan.baidu.com/s/1ksgRwVjzzZyUSfC_5qevUA?pwd=jd8v",
    "https://pan.baidu.com/s/1CFUAtDroGG-pAh_45CCccQ?pwd=mne7",
    "https://pan.baidu.com/s/1QQYFW6sjvg4WLWztvacFPA?pwd=b4y3",
    "https://pan.baidu.com/s/1Z2LDMt3fcY55Y-ZTpPNWCg?pwd=cd5p",
    "https://pan.baidu.com/s/1xt1qOKuxKj5mQjKZbIuaqQ?pwd=ttcx",
    "https://pan.baidu.com/s/1_rOZwJ72lEezvunwjmqMWg?pwd=g84t",
    "https://pan.baidu.com/s/1BxSpPXTnlmDT_4VIb9wr_g?pwd=115w",
    "https://pan.baidu.com/s/11qUj1qWGivtwk1m1b4Etlg?pwd=vga3",
    "https://pan.baidu.com/s/1i2YQxCKGNhYtUm0msvFung?pwd=dsnh",
    "https://pan.baidu.com/s/1K2rBHVk5OX8svkLzxWDPVg?pwd=9imm",
    "https://pan.baidu.com/s/1qQayAFkyAFnr0RCiHF2kbA?pwd=x6wf",
    "https://pan.baidu.com/s/1i31wSoucBzj6PgCnnns34Q?pwd=s8kn",
    "https://pan.baidu.com/s/1vUg6BqucEuuUgJ-qbo0rFg?pwd=ubwp",
    "https://pan.baidu.com/s/1FWkj8uaWM2omNQAH5Lrcgw?pwd=4r3i",
    "https://pan.baidu.com/s/16u5FAkVshSmhysYhFPEVfw?pwd=ftf6",
    "https://pan.baidu.com/s/1EawS4lzv3kFZf9B3Bvvoyg?pwd=h8ee",
    "https://pan.baidu.com/s/1BVFMWiy5c4j9s_v3TsLonQ?pwd=2cxm",
    "https://pan.baidu.com/s/1LQlAXjyhY-VeAzzKpdiQ6Q?pwd=789b",
    "https://pan.baidu.com/s/1wtOxTjOiOf8xTcIXkuCv0w?pwd=3yp3",
    "https://pan.baidu.com/s/1MMzTYMTuF_dR5xASoZEN6A?pwd=am99",
]

TEST_LINKS = [
    "https://pan.baidu.com/share/init?surl=2UvUofV1eOoEA_bElixaDQ&pwd=yezi"
]

# baidu pan walk (read-only listing, scripts/walk_share.py)
# WALK_LINKS = BANGUMI_LINKS[:3]
WALK_LINKS = TEST_LINKS