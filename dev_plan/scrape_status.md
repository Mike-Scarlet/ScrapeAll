# 抓取链路现状 — cangku / eroscripts

> 最后更新：2026-08-24（consume 升包 + 存量补标当日，数据为 `data/` 实库核对）

## 0. 总览

两条链路同构：**collect → fetch → parse 三阶段流水线，sqlite 状态机驱动**，每阶段独立入口、可中断重跑，stat 队列即任务队列。三阶段代码均已完成并各自全量跑过一轮，`history_done` 标志均已置位（增量模式就绪）。

**cangku 的 consume 已接线**（2026-08-24，见第 1.7 节）：stat=2 队列已清空（35 帖 → 34 CONSUMED + 1 SHARE_DEAD），增量帖照常进队。**eroscripts 的 consume 仍在前沿**：下载基建 adapter 按序接入中（第 3 节），stat 2→3 无人调用。

| 链路 | collect | fetch | parse | consume |
|---|---|---|---|---|
| cangku（yejiang 用户帖） | ✅ 全量回填完成 | ✅ 100 HTML 落盘 | ✅ 35 帖产出链接 | ✅ 已升包接线，存量清零 |
| eroscripts（discourse loli tag） | ✅ 1800 topic 收齐 | ✅ 1154 JSON 落盘，0 失败 | ✅ 1152 帖产出链接 | ❌ 未开始 |

### stat 状态机（两条链路语义一致）

| stat | 含义 | 说明 |
|---|---|---|
| 0 | DISCOVERED | 列表 walk 出来，仅有列表 meta |
| 1 | FETCHED | 详情页已抓取落盘（可离线重试） |
| 2 | PARSED | 工况内，links_json 已写入 |
| 3 | CONSUMED | 已交后续流程（终态）；**cangku 已有调用方**（转存成功或增量对比后全已覆盖） |
| 4 | OUT_OF_SCOPE | 工况外（终态） |
| 5 | DEFERRED | 结构超规挂起，非失败；`--retry-deferred` 收编 |
| 6 | SHARE_DEAD | 分享链接已失效（打开即 share invalid，终态）；**仅 cangku 在用**，作者更新帖被 collect 重置回 0 自然重试 |
| -1 / -2 | FETCH_FAILED / PARSE_FAILED | 两边实跑均为 0 |

## 1. cangku（cangku.moe / yejiang=309550 用户帖）

**目标**：抓作者帖子 → 解析帖子页合集 box 里的百度网盘项 → 二维码解码出 pan 链接 → 供百度盘转存。

### 1.1 数据现状（2026-08-24 实库）

- `data/cangku.db`（表 `PostItem`）：**100 帖 = 34 已消费(3) + 63 工况外(4) + 2 挂起(5) + 1 分享死链(6)**，零失败；stat=2 队列已清空（8-24 存量补标）
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

1. ~~stat 2→3 消费标记未接线~~ → 已接线（1.7 节，2026-08-24）
2. 2 个 deferred 帖待补规则收编
3. cangku 有完整 store 单测（test_cangku_store.py），无缺口

### 1.7 consume（2026-08-24 升包接线）

原 playground 转存编排（bd_orchestrate*.py，8-18 已全量真跑验证过）升包：

- **编排逻辑** `scrape_all/sites/baidu_pan/orchestrate.py`：分享根按作者分道（本地库无记录整目录全转存 / 已匹配作者 walk 到月份层增量对比：重抓最后月+未覆盖月，重抓月只补本地没有的子项）、CREATOR_ALIASES 别名表、`load_local_months` 装配；单测 `tests/test_baidu_pan_orchestrate.py`（9 例，断言迁自 _logic_selftest.py）
- **入口** `scripts/consume_posts.py`：默认 dry-run（walk+选点+打印计划，不动 stat）；`--execute` 真跑（首个非空计划前输 yes，`--yes` 跳过）；`--smoke/--ids/--limit` 选帖。流水式逐链接执行，报告落 `data/consume_report.txt`
- **stat 流转**（仅 --execute）：share invalid → 6；计划空（全已覆盖）或全 op 成功 → 3；打开/walk 失败（非死链）或部分 op 失败 → 保持 2 下轮重试
- **SHARE_DEAD(6) 语义**：终态；作者更新帖 → collect 时间戳变化 → 重置回 0 重走全程，死链补偿（原 TODO 3）就此闭环，无需额外机制
- **存量补标**（`playground/_mark_consumed_backlog.py`，证据链从 bd_full_real_run/bd_smoke 日志解析）：8-18 真跑成功的 33 帖 + 冒烟 219782 → 3，死链 225111（山含）→ 6；补标前备份 `data/db_backup/`
- 已知取舍：部分失败帖重跑会把已成功 op 再转一遍（现接受重复，与升级前 --ids 手动补跑一致）

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
  - `gofile`（55 条，全部 /d/{id}）：**页面流版，全链路验证通过**（2026-08-23）。死链 http 仍 200，判死靠 SPA 渲染后 title `Content not found · Gofile`；活页文件行 `div.fm-row`、真名在 `button[data-action="item-menu"]` 的 aria-label、点 `button[data-action="download"]` 直接出下载事件（无广告中转）。固定 19 条验证：14 死 / 5 活（gofile 不活跃删内容，库内死亡率 ~74%）；真实下载 2 条小活链（5.3MB + 1.6MB 各 2 文件）落盘名体积全对，幂等复跑 skipped 零流量。渲染慢的页（>15s）判 unknown 不误判死，重试可解（4J4SjB 实例）
  - `mega`（208 条，131 folder + 68 file，密钥在 URL hash）：**页面流版，全链路验证通过**（2026-08-24，含两轮人工指认元素）。死链 http 200 且 title 正常演化成 'Download - MEGA' 不可信，判死靠正文三种文案（无法访问该文件/该文件夹不再可用/此内容已被移除）；file 页名/体积在 `.dl-header .fileinfo`（.name+.ext 分开、.size 是 nbsp+小写单位），下载按钮 = header 图标按钮 `button[data-simpletip="下载"]`；folder 页行 = `a.mega-node.fm-item`（是 `<a>` 不是 tr！），体积+名在 title 属性（mp4 行带 "1280x1080 @30fps" 前缀，体积解析词边界锚定）。**下载全部页面内完成**：分块拉取 userstorage → 内存解密 →（folder 打包 zip）→ 浏览器下载事件，事件时间 ≈ 体积/网速（39.5MB=14s），等待超时 5 分钟。**folder 刻意走整夹 ZIP**（不选中任何行 → `button.fm-download` → 「下载为ZIP」，suggested=文件夹真名.zip）——绕开选中态语义（实测有"点了 A 下成 B"未解之谜，不依赖）；偶发「连接桌面应用程序」sheet 有看门狗点『好的，明白了』关掉。近期链接存活率截然不同：2026-04 前老样本 3/3 死，06-08 近期 6/6 活。adapter 验证 6 探活全对 + 幂等零流量 + J1tViZLa 整夹 ZIP 38,954,648B 落盘完整性 OK（7 条目，主 funscript 合法 JSON）；另 playground 直测 isami_ride.mp4 49,202,734B 与 API 字节数逐字节一致。已知限制：folder ZIP 幂等只能事件后判（zip 名=文件夹真名，点击前读不到），复跑会重拉一遍
- **剩余 host 决定不接**（2026-08-24，量少人工更划算）：近期（2026-04 后）未接家仅 yandex 2 条 + docs.google 1 条（spreadsheet 该重分类）；gdrive 6 / workupload 17 / mediafire 4 / yandex 3 / pan.baidu 1 / dropbox 1 全是 4 月前老存量。这些 host 的链接登记进 EroLink 时直接置 manual，人工经 `scripts/ero_links.py` 处理
- 验证入口：`scripts/probe_downloader.py`（只动 `data/eroscripts/files/_verify/`，不碰 stat 不建任务表）
- **链接级状态落库**（`EroLink` 表，2026-08-24）：url 主键去重（跨 topic 共享一行只下一次，顺手解决 mega folder ZIP 幂等只能事件后判的复跑重拉）。两层状态：`probe_status` 记探活证据（pending/alive/dead/needs_auth/paywall/unknown），`dl_status` 记处置（在途 pending/failed；终态 downloaded/skipped/dead/manual/exhausted）。**topic 级 CONSUMED 判定只看 dl_status 全终态**（manual/exhausted 也算——不让人工/放弃盘点卡住消费闭环），死链走链接级 dead 不需要帖级 SHARE_DEAD。重试上限 1 次共 2 次尝试，耗尽转 exhausted（与 manual 分开：manual 预期人介入，exhausted 仅自动放弃）。`upsert_links` 幂等：已存在行绝不动状态，重跑 parse 不清进度。人工渠道 `scripts/ero_links.py`（counts/list/set）：set 可改任意合法状态，改回 pending 清零重试计数重走自动流程（probe unknown 连带重置，alive/dead 证据保留）。store 层单测补齐（18 例，含 TopicStore 基础流转——eros store 测试缺口就此收掉），全量 210 passed

## 4. 共同前沿：consume 阶段

**cangku 侧已完成**（1.7 节）：编排升包 + stat 2→3/6 流转 + 死链补偿闭环 + 存量清零。

**eroscripts 侧**：链接级记账已落表（2026-08-24，EroLink——见第 3 节末，当时"届时需新表"的判断已兑现）。剩编排器：stat=2 的 1152 帖（去重 5987 链接：script 2701 / media 1219 / source 800 / other 1267）先 `upsert_links` 登记（零流量），再 probe → download 流水（对齐 cangku `consume_posts.py` 模式：dry-run 默认、`--execute` 才动 stat、流水式逐链接可断点重跑）。死链量大（gofile ~74%）由链接级 dead 终态吸收，不影响 topic 判定。

原出处（已随 cangku 升包解决）：`playground/bd_orchestrate.py:18-28` 的 TODO 块。

---

## 附：常用巡检

```
python -m pytest scrape_all/tests        # 全部纯逻辑单测，不碰浏览器
python data/_stat.py                     # cangku stat 分布 + fetch failed 列表
python data/_check_links.py              # cangku 打印 stat=2 links
python scripts/consume_posts.py          # cangku consume dry-run（不动 stat）
python playground/_check_eros_db.py      # eroscripts 总量/stat/flags
python playground/_check_eros_deferred.py # eroscripts 挂起帖及其链接
```
