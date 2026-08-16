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
python -m pytest scrape_all/tests   # 单测（纯逻辑，不需要浏览器）
```

## 依赖

```
pip install -r requirements.txt
pip install -e <python_general_lib 本地路径>
```

for linux - when stuck, need to check out bash can access google, export proxy if needed
