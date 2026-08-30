# playground 历史脚本索引（2026-08-30 清理）

playground 遵循生命周期：**探查 → 原型 → 上岸（scrape_all/ + scripts/）→ 放量随迁脚本**。
本目录索引 2026-08-30 清理删掉的约 124 个已完成使命的脚本——文件在 git 历史
（清理 commit 之前）永远可捞，这里只记"每组的知识沉淀在哪"，免得考古时无从下手。

同名前缀约定：删掉的脚本名与 git 历史一致，`git log --diff-filter=D --name-only`
或直接按路径 `git show <旧commit>:<路径>` 取回。

| 删除组（原路径 playground/…） | 知识去向 |
|---|---|
| `baidu_pan/orchestrate/`（bd_orchestrate 真跑/dry-run/逻辑自测） | 升包 `scrape_all/sites/baidu_pan/orchestrate.py` + `scripts/consume_posts.py` + `tests/test_baidu_pan_orchestrate.py`（commit fad9929；8-18 全量真跑记录在 dev_plan §1.7） |
| `baidu_pan/debug/`（goto-after-dialog 之谜、Erio 冒烟补欠） | 之谜已解并加固进升包后的执行器；结论在 dev_plan §1.7 与升包代码内 |
| `baidu_pan/checks/`（_mark_consumed_backlog 存量补标等） | 补标证据链记录在 dev_plan §1.7"存量补标"条目 |
| `downloader/gofile/`（observe×5 / pick×3 adapter 开发系列） | adapter 上线 `scrape_all/downloader/adapters/gofile.py`；页面语义/坑在 dev_plan §3 gofile 条 + commit 8d9166f |
| `downloader/mega/`（observe×7 / verify / probe 诊断 + _mega_diag 截图×8） | adapter 上线（commit ea83796、c58e78f 双视图修复）；选择器细节在 dev_plan §3 mega 条 + `tests/test_downloader_mega.py` |
| `downloader/pixeldrain/`（debug_pd 系列 / /d 捞回 / 放量快照） | adapter 上线（commit 67b86b9）；/d 误判根因修复 8813171；放量收尾 e5e06cd |
| `downloader/hanime/` 放量随迁 13 个（flip/reset/revive/audit/pick） | 该站 80/80 downloaded 清零；实录在 commit be6677c（attachment 直链岔路）、8ef9c93（撞名误判）；**保留**了 5 个 ps1 观测组 + `_hold_hanime.py`（通用工具，仍在 playground） |
| `eroscripts/probe/`（p1–p8 建站探查） | 分页规则进了 `scrape_all/sites/eroscripts/api.py` 头注释；坑在 dev_plan §2.2 |
| `eroscripts/peek/`（host 普查 / catbox 审计） | host 接入顺序决策记录在 dev_plan §3"剩余 host 决定不接" |
| `eroscripts/consume/`（放量期间快照×6） | 编排器放量实录在 commit 2f0f11a（52 帖收口） |
| `eroscripts/checks/` 已结案取证（320427 串包×4、salvage×3、audit×3、pd_* 调查×9、collision、extract_failed、stat2_host_mix、topic_peek、zip_newest、zip_topic_dist） | 串包收尾 bb086af（EroExtract 现 105/105 done）；同名覆盖修复 66d0526；/d 形态语义 8813171；全部闭环 |
| `eroscripts/stats/` 老一代（_script_only_stats、_audit_stat2_covered） | 被 `_streaming_coverage.py`（保留）接棒；盘点报告存本目录 `_script_only_topics.md`（含"疑似解析漏网 4 帖"待办信号） |
| `local_library/checks/`×5 | merge/scan 升包 `scripts/local_library.py`（commit b835b0d）带单测 |

清理后 playground 仍保留的四类（详见 `playground/README.md`）：
eros 库巡检×5、4.2 配对原型×7、加密 rar 人工补解配方、hanime 通用观测组、stats 现役×3。

更早期（2026-07 前）的平铺 playground 脚本就是本目录下的 `playground-*.py` 六个。
