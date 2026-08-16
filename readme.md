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
  storage/     sqlite 存储模型
  tests/       pytest 单测（假树测试纯逻辑，不碰浏览器）
data/          运行数据（gitignore）
archive/       历史实验脚本
```

## 运行

依赖系统安装的 Chrome（`channel: chrome`），登录态持久化在 `browser_session/`，首次运行按提示人工登录一次即可。

```
python scripts/scrape_yejiang.py    # 抓取仓库站用户帖子
python scripts/save_bangumi.py      # 批量转存 config.py 里的分享链接
python scripts/walk_share.py        # 只读遍历分享目录树（WALK_LINKS），打印树
python scripts/save_partial.py --dry-run   # 只读：遍历 + 打印部分转存计划
python scripts/save_partial.py      # 遍历 + 打印计划 + 输入 yes 确认后执行转存
python scripts/verify_save_chain.py # 只读预检：转存链路全走一遍但不点确认不建目录
python -m pytest scrape_all/tests   # 单测（纯逻辑，不需要浏览器）
```

## 代码来源（重构前后对比）

重构前旧代码约 520 行，现在 baidu_pan 包 + 测试 + 脚本约 1760 行，其中约 2/3 新写、1/3 复用：

- 新写（~1150 行）：`tree.py` 遍历与停止策略、`save_plan.py` 转存计划、`save_executor.py` 执行编排、hash 深链导航（`goto_path` + URL 工具函数）、`list_files` 的 size/mtime 解析与同级同名检测、全部单测（495 行）、`walk_share.py` / `save_partial.py` / `verify_save_chain.py`
- 复用旧功能（~560 行）：`SaveDialog`（弹窗树导航、新建文件夹、确认）、`SharedLinkPage` 的密码进入 / 列表解析 / 勾选交互、`login` / `predicates` / 选择器、`save_bangumi.py` 批量转存流程

决策层（遍历、计划、执行、测试）全新，页面动作层沿用已验证的旧实现。

## 依赖

```
pip install -r requirements.txt
pip install -e <python_general_lib 本地路径>
```

for linux - when stuck, need to check out bash can access google, export proxy if needed
