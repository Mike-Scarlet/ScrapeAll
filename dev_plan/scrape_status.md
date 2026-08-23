# 抓取链路现状 — cangku / eroscripts

> 最后更新：2026-08-23（基于 git `6e51910`，数据为 `data/` 实库当日核对）

## 0. 总览

两条链路同构：**collect → fetch → parse 三阶段流水线，sqlite 状态机驱动**，每阶段独立入口、可中断重跑，stat 队列即任务队列。三阶段代码均已完成并各自全量跑过一轮，`history_done` 标志均已置位（增量模式就绪）。

**共同的前沿边界：parse 产出（stat=2）之后的 consume 阶段未接线** —— CONSUMED(3) 状态定义了但无调用方，下游转存编排活在 `playground/` 未升包（详见第 4 节）。

| 链路 | collect | fetch | parse | consume |
|---|---|---|---|---|
| cangku（yejiang 用户帖） | ✅ 全量回填完成 | ✅ 100 HTML 落盘 | ✅ 35 帖产出链接 | ❌ 未接线 |
| eroscripts（discourse loli tag） | ✅ 1800 topic 收齐 | ✅ 1154 JSON 落盘，0 失败 | ✅ 1152 帖产出链接 | ❌ 未开始 |

### stat 状态机（两条链路语义一致）

| stat | 含义 | 说明 |
|---|---|---|
| 0 | DISCOVERED | 列表 walk 出来，仅有列表 meta |
| 1 | FETCHED | 详情页已抓取落盘（可离线重试） |
| 2 | PARSED | 工况内，links_json 已写入 |
| 3 | CONSUMED | 已交后续流程（终态）**—— 两边都无人调用** |
| 4 | OUT_OF_SCOPE | 工况外（终态） |
| 5 | DEFERRED | 结构超规挂起，非失败；`--retry-deferred` 收编 |
| -1 / -2 | FETCH_FAILED / PARSE_FAILED | 两边实跑均为 0 |

## 1. cangku（cangku.moe / yejiang=309550 用户帖）

**目标**：抓作者帖子 → 解析帖子页合集 box 里的百度网盘项 → 二维码解码出 pan 链接 → 供百度盘转存。

### 1.1 数据现状（2026-08-23 实库）

- `data/cangku.db`（表 `PostItem`）：**100 帖 = 35 已解析(2) + 63 工况外(4) + 2 挂起(5)**，零失败
- `history_done` 已置位（key `yejiang:309550:history_done`），增量跑遇已覆盖帖即停
- 落盘：`data/cangku/posts/` 100 个帖子 HTML；`data/cangku/qr/` 58 张二维码原图（调试留档）
- **挂起待收编**（规则补全后 `parse_posts.py --retry-deferred`）：
  - `228540` 芙丽莲（度盘/552MB）
  - `225355` Tera Stellar

### 1.2 各阶段

- **collect** `scripts/scrape_yejiang.py`：登录（阻塞人工一次）→ 翻 `user/309550/post?page=N` 到 cutoff（2025-12-01，含该时刻）/已覆盖边界。异步卡片填充轮询等 DOM 稳定再取 outerHTML。stop_reason 只有 `reached_cutoff` / `empty_page` 才置 `history_done`。
- **fetch** `scripts/fetch_posts.py`：stat=0 逐帖取帖子页 HTML 落盘（0→1，超时→-1），500ms 温和间隔。就绪等待 `article.article` 而非分类 label（没挂标签的帖等 label 会永远超时，225885 教训）。
- **parse** `scripts/parse_posts.py`：本地 HTML 离线解析（1→2/4/5/-2）。**关键区分**：取二维码图全部成功但结构超规 → 确定性挂起(5)；取图有失败 → 可能是暂时网络问题，保持原状态下轮再试。
- **辅助**：`scripts/probe_cangku.py`（只读探针）、`scripts/pass_cdn_challenge.py`（人工过图床 CF 挑战，cf_clearance 存持久 profile）。

### 1.3 解析覆盖面（`scrape_all/sites/cangku/post_filter.py`）

- 分类门严格：meta-label 含「动画」才工况内，**没挂标签也算外**；`CANGKU_FORCE_IDS`（config.py:12）后门按 id 跳过分类检查，现收了漏挂的 225885
- 合集 dl-box：折叠卡标题含「合集」——Vue 只是视觉折叠 DOM 全量渲染，不用真点开
- 密码提取：「提取(码)」「(解压)密码」两套正则
- 只取名字带「百度」的项（Pikpak 等同盒其他项跳过不记异常）；pan_type 看二维码内容不看按钮名
- 直链形态（项地址本身是 pan.baidu.com 链接）直接采用不解码
- 判 anomaly（→挂起 5）的情况：工况内但没有合集卡 / box 无下载项 / box 无百度项 / 百度项无二维码地址 / 取图解码失败 / 解码内容非网盘链接

### 1.4 二维码链路（`scrape_all/sites/cangku/qr.py`）

- 取图必须走 playwright 页：CDN 对代理出口 IP、python TLS 指纹都拉黑；favicon 代理接口只回 32x32 缩略图解不出
- CF 挑战：patchright stealth（BrowserSession(stealth=True)）+ 403/503 HTML 判挑战页 → 停窗等人工过，3s 轮询上限 300s
- 解码链：**wechat QR（cv2.wechat_qrcode_WeChatQRCode）优先**（艺术二维码中间叠人物图也能解）→ 失败走 QRCodeDetector 兜底：原图 → OTSU 二值化 → 2x → 3x 放大
- 早期实验脚本存档在 `archive/opencv_qrdecode*.py`

### 1.5 增量机制

- 去重键 (url, 时间戳)，url 主键；时间归一化到秒级 naive UTC（支持 ISO/5 种绝对格式/相对时间）
- 更新帖：刷新 title/post_time，stat 重置回 0、清 links_json，**保留 first_seen**
- `history_done` 置位前不因已覆盖帖停页（回填要把更深页抓完），置位后增量遇已覆盖即停
- 更新帖时间戳上浮不会被边界挡住（边界后仍扫完本页）

### 1.6 遗留

1. stat 2→3 消费标记未接线（见第 4 节）
2. 2 个 deferred 帖待补规则收编
3. cangku 有完整 store 单测（test_cangku_store.py），无缺口

## 2. eroscripts（discuss.eroscripts.com / loli tag / Scripts 分类）

**目标**：loli tag 下 Scripts 分类（category_id=14）的 topic → 提取 funscript 脚本链接与媒体下载链接。

### 2.1 数据现状（2026-08-23 实库）

- `data/eroscripts.db`（表 `EroTopicItem`）：**1800 topic = 1152 已解析(2) + 646 工况外(4) + 2 挂起(5)**，零失败
- `history_done` 已置位（key `eros:tag:loli:history_done`）；全量回填 61 页翻到空页（PAGE_LIMIT=100 内余量充足）
- 落盘：`data/eroscripts/topics/` 1154 个 topic JSON（**工况外的也落盘**备复核）
- 链接统计（实库现算）：**script 2728 / media 1246 / source 856 / other 2506 条**；topic 覆盖 script 1142 / media 875 / source 550 / other 982
- **挂起待收编**：`111424`（Ikumonogakari）、`312646`（Mokusheep）；全量回填日志时是 4 个，170447/168095 其后已收编
- 库检查脚本：`playground/_check_eros_{db,cat,links,cdn,deferred}.py`

### 2.2 各阶段（统一入口 `scripts/scrape_eroscripts.py`）

- `--stage all`（默认）跑全流程；`--stage collect|fetch|parse` 单跑；parse 可加 `--retry-deferred`（连挂起重跑）和 `--reparse`（连 stat=2 离线重分类，域名表升级用，不用重抓）；collect 可加 `--full-history`（清 history_done、忽略 cutoff 翻到底）
- **collect**：不扒 DOM，playwright 站内页 `page.evaluate` 同源 fetch `{tag_url}.json`（走浏览器登录态+指纹，绕 CDN 限制）。坑：tag 列表第 2 页起 `?page=N` 是服务端缓存快照滞后数天，靠 topic_id 去重吸收；429 按 body 的 wait_seconds 退避，页间隔 1.2s
- **fetch**：pending（stat=0）逐 topic 取 `/t/<id>.json`（用 id 不用 slug，slug 会随改名变）；列表 meta cat≠14 直接批量置工况外不发请求，topic JSON 内 category_id 二次复核。**有意取舍：只抓 OP + 前 20 楼**（Discourse chunk_size），更深作者更新会漏
- **parse**：离线读盘，BeautifulSoup 按 DOM 顺序收 `<a>`，记录小节标题/楼层/用户名上下文；`<code>/<pre>` 补裸 URL 正则；站内链接只收 `/uploads/` 附件。link_kind 优先级：附件标记 → 扩展名（.funscript/.lua/视频）→ funscript 字样打包直链 → 域名表（MEDIA_HOSTS 网盘 / SOURCE_HOSTS 流媒体，**已按首轮 other 分布补过一轮**）→ other。links_json 全量落库含 other

### 2.3 增量机制

- topic_id 主键（不以 url 为键，slug 会变）；bumped_at **秒级归一化**比对（防毫秒 vs 秒永远误判为被顶起）
- 被回复顶起（bumped_at 变新）→ 判更新 → 重置回 stat=0 清 links_json 重走全程
- pinned 帖浮在页首不受排序保证，豁免触底/边界判定

### 2.4 遗留

1. stat=3 消费未开始（见第 4 节）
2. 2 个 deferred 帖待人工过目收编
3. **other 域名表不完整**：2506 条 other，头部是 patreon（555+80）、fantia（134）、sankakucomplex（132）、thehandy（128）、pixiv（119）、x.com（83）等 —— parse 结尾会打印 Top15 供补表，补完 `--reparse` 离线重分类
4. store 层**无单测**（cangku 有 test_cangku_store.py，eroscripts 是唯一测试缺口）
5. `-1/-2` 无专门 retry 参数（实跑 0 失败，暂无影响）
6. `store.py:113` 注释过时（"首版只用到 collect"，实际 fetch/parse 已在用）

## 3. 下载基建（scrape_all/downloader/，2026-08-23 起）

eroscripts consume 的第一步：**逐家文件托管做单链接可信的 probe/download adapter，批量编排后置**。约定：所有取回走浏览器页（真实 Chrome 指纹 + browser_session/ 持久 profile 登录态 + DOWNLOADER_PROXY 代理），并发默认 1 串行（引擎级信号量 + origin 页级锁）；落盘名经 Windows 合法性清洗（非法字符替换、保留名前缀、截断保扩展名）。

- **engine**（`scrape_all/downloader/engine.py`）三原语：`probe_headers`（同源页内 Range:0-0 探活，读到头即 abort 不下数据）、`blob_download`（同源页内 fetch→blob→浏览器下载事件，中小文件）、`direct_download`（goto 触发浏览器下载器，依赖 attachment 头，大文件流式落盘）。park 机制：goto commit 后立刻 window.stop() 停在目标 origin，防 inline 渲染白吞流量
- **adapter 契约**（`adapters/base.py`）：`probe -> ProbeResult(alive/dead/needs_auth/paywall/unknown + 真名/大小/文件夹清单)`、`download -> DownloadResult(downloaded/dead/failed/skipped)`；Range 探活的 size 解析和 content-disposition 原始文件名解析是共用 helper
- **已接入并真链接验证**：
  - `catbox`：23 条库内链接探活 19 活 / 2 死（404 判死正确）/ 2 unknown（litter.catbox.moe 子域网络层整体取不动，不误判死）；8.5MB mp4 走 blob 真实落盘，magic bytes 合法
  - `eros uploads`（站内脚本附件 2693 条）：discourse 附件带 attachment 头，probe 停站点根页同源 fetch（206 + content-disposition 拿到原始文件名和大小），download 走 direct_download；3 个 funscript 落盘，大小逐字节对上，内容校验为合法 funscript JSON（actions 数组在）
  - 踩坑记录：attachment URL 的 goto 会 net::ERR_ABORTED——这是"下载已开始"的正常信号，engine 里吞掉该错误由 expect_download 接手
  - `pixeldrain`（905 条主力，库内 /l 431、/d 259、/u 205、/api 1）：**页面流版，全链路验证通过**（2026-08-23 `_verify_pd_final`）。probe/download 都是开真实页面读渲染结果——文件页 title=文件名、`.stat` 文本=人读体积，title "404, …Not Found" 或 http 404/410 判死；download 在点击前做幂等检查（已存在直接 skipped 不点按钮），文件页点 `button.toolbar_button`、列表页点 `button[title*="zip archive"]` 整包 zip。最终验证 4 步全过：4 条已知链接探活全对（活文件拿到真名+体积、死链 404）、幂等 skipped、51MB mp4 真实点击下载落盘（51092113 字节）、列表按钮点击→下载事件→立刻 cancel。注意：`/api/file/{id}` 返回的是**文件本体**不是元信息 JSON（曾因此把 1.8GB 拉进流式读），按约定 adapter 不走 API
- **待接入**（按序）：gofile（55，全部 /d/{id} 形态）→ mega（208，139 folder / 69 file，folder 密钥在 hash）→ gdrive（6 条 drive.google.com；另有 7 条 docs.google.com 是 spreadsheets 不是文件，应重分类）→ workupload（17，11 /file/ + 6 /archive/，人机验证）
- 验证入口：`scripts/probe_downloader.py`（只动 `data/eroscripts/files/_verify/`，不碰 stat 不建任务表）

## 4. 共同前沿：consume 阶段（挂账 TODO）

出处：`playground/bd_orchestrate.py:18-28` 的 TODO 块 + `data`/`playground` 实况。转存编排（选点、按作者分道、逐链接流水执行、三级恢复）已在 playground 验证过真转存（bd_full_real_run 等日志），但未升包。

挂账三件事：

1. **编排逻辑升包**：select_ops / make_policy / 执行编排从 `playground/bd_orchestrate*.py` 升进 `scrape_all.sites.baidu_pan`，scripts/ 出正式入口
2. **stat 2→3 消费标记**：粒度（帖子级 or 链接级）、失败 op 是否阻止升级、死链帖留 2 还是单列 —— 待定。现状事实实现：dryrun 直接 SQL 读 cangku.db stat=2 的 links_json 做选点
3. **死链补偿**：库内分享已被作者删的（已知：山含 225111）

建议顺序：升包 → 消费标记语义定稿 → 死链补偿策略随标记一起落地。

---

## 附：常用巡检

```
python -m pytest scrape_all/tests        # 全部纯逻辑单测，不碰浏览器
python data/_stat.py                     # cangku stat 分布 + fetch failed 列表
python data/_check_links.py              # cangku 打印 stat=2 links
python playground/_check_eros_db.py      # eroscripts 总量/stat/flags
python playground/_check_eros_deferred.py # eroscripts 挂起帖及其链接
```
