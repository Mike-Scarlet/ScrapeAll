# ScrapeAll

从 cangku.moe 抓取动画资源帖，解析其中的百度网盘分享链接，并自动转存到自己网盘的浏览器自动化工具（Playwright）。

## 目录结构

```
scripts/       入口脚本
config.py      运行配置：代理、用户 id、转存目标路径、分享链接清单
scrape_all/    核心包
  browser/     Playwright 浏览器上下文（复用 browser_session/ 保留登录态）
  sites/       站点封装
    cangku/    cangku.moe 抓取
    baidu_pan/ 百度网盘分享页打开 / 文件树导航 / 转存
  local_library/ NAS 已确认库（erodouga/creators/[4]confirmed）状态镜像 + yejiang 目录归整
  storage/     sqlite 存储模型
  tests/       pytest 单测（假树测试纯逻辑，不碰浏览器）
data/          运行数据（gitignore）
archive/       历史实验脚本
```

## 运行

依赖系统安装的 Chrome（`channel: chrome`），登录态持久化在 `browser_session/`，首次运行按提示人工登录一次即可。

```
python scripts/probe_cangku.py     # cangku 解析探针：分类过滤 + 合集 box 解析，浏览器取二维码解码出网盘链接
python scripts/pass_cdn_challenge.py # 手动过图床 Cloudflare 挑战（cf_clearance 存持久 profile，按域名各过一次）
python scripts/scrape_yejiang.py    # cangku collect：翻用户帖子列表到 cutoff/已覆盖边界，新帖/更新帖落库（增量安全）
python scripts/fetch_posts.py       # cangku fetch：待抓帖子页逐帖存 HTML 到本地（stat 0 -> 1/-1）
python scripts/parse_posts.py       # cangku parse：本地 HTML -> 链接落库（1->2）、工况外（->4）、结构超规挂起（->5，加 --retry-deferred 连挂起帖重跑）
python scripts/save_bangumi.py      # 批量转存 config.py 里的分享链接
python scripts/walk_share.py        # 只读遍历分享目录树（WALK_LINKS），打印树
python scripts/save_partial.py --dry-run   # 只读：遍历 + 打印部分转存计划
python scripts/save_partial.py      # 遍历 + 打印计划 + 输入 yes 确认后执行转存
python scripts/verify_save_chain.py # 只读预检：转存链路全走一遍但不点确认不建目录
python scripts/local_library.py scan   # 扫描 NAS 库根（[4]confirmed）的 yejiang 夹 -> data/local_library.db；工况外只报告
python scripts/local_library.py move   # dry-run 打印搬运计划："作者名 {YY.MM} [yejiang]" -> [yejiang]/作者名/（同卷 rename）
python scripts/local_library.py move --confirm  # 交互确认后真搬；搬运后日期只在库内 folder_date 维护
python -m pytest scrape_all/tests   # 单测（纯逻辑，不需要浏览器）
```

## 代码来源（重构前后对比）

重构前旧代码约 520 行，现在 baidu_pan 包 + 测试 + 脚本约 1760 行，其中约 2/3 新写、1/3 复用：

- 新写（~1150 行）：`tree.py` 遍历与停止策略、`save_plan.py` 转存计划、`save_executor.py` 执行编排、hash 深链导航（`goto_path` + URL 工具函数）、`list_files` 的 size/mtime 解析与同级同名检测、全部单测（495 行）、`walk_share.py` / `save_partial.py` / `verify_save_chain.py`
- 复用旧功能（~560 行）：`SaveDialog`（弹窗树导航、新建文件夹、确认）、`SharedLinkPage` 的密码进入 / 列表解析 / 勾选交互、`login` / `predicates` / 选择器、`save_bangumi.py` 批量转存流程

决策层（遍历、计划、执行、测试）全新，页面动作层沿用已验证的旧实现。

## 提交规范

Conventional Commits：`feat(范围): 摘要` / `fix(范围): 摘要` / `docs: 摘要` 等，范围为模块名（`cangku` / `baidu_pan` / `local_library` / `readme` ...）。

## 依赖

```
pip install -r requirements.txt
pip install -e <python_general_lib 本地路径>
```

for linux - when stuck, need to check out bash can access google, export proxy if needed
