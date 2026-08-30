# playground —— 探查与原型工作区

生命周期：**探查 → 原型 → 上岸（scrape_all/ + scripts/ + tests/）→ 随迁脚本随放量结案删除**。
2026-08-30 大清理后只留少量活着的东西（后续新增随验随记）；删掉的约 124 个脚本的
知识去向见 `archive/playground_history/README.md`（git 历史永远可捞）。

## 现存清单

```
eroscripts/checks/   库巡检 + 4.2 配对原型
  _check_eros_{db,cat,links,cdn,deferred}.py  # 常用巡检（dev_plan 附录引用）
  _pairing_report.py        # funscript↔视频分层配对原型（exact→轴变体→NFKC 模糊），
                            #  dev_plan §4.2 配对决策表的直接前身
  _duration_match_trial.py / _duration_signal_probe.py / _signal_coverage_census.py
                            # 时长兜底 ±2s 的信号覆盖与最难案例实测
  _disk_ext_census.py / _zip_census.py / _zip_census_followup.py
                            # 盘面扩展名分布 / 档案普查（"88/91 混合包自配对"出处）
  _rar_manual_extract.py    # 加密 rar 人工补解配方（复用 extract.extract_rar_file，
                            #  未来遇到加密包照此改topic/密码即可）
eroscripts/stats/    现役只读盘点（--since 参数化，可重跑）
  _streaming_coverage.py    # source 覆盖度 + EroLink 闭环（报告落 data/）
  _downloaded_since.py / _media_hosts_of_script_only.py
downloader/hanime/   通用观测工具（与站点无关，大件下载调试都用得上）
  _hold_hanime.py            # 同 profile+代理+stealth 开页停窗，人工过验证/观察（argv 传 URL）
  _blob_progress.ps1         # chrome blob_storage 分片体积（判断大件是否在推进）
  _find_crdownload.ps1 / _find_growing.ps1   # 找 .crdownload 在途件 / 找增长中文件
  _proc_snapshot.ps1 / _watch_chrome_mem.ps1 # chrome 进程快照 / 内存盯梢
```

## 约定

- 脚本一律下划线前缀；只读的注明"只读"；写库的注明动哪张表。
- 涉及网络/浏览器的遵循 WORK_RULES.md（批量先报数，单链接验证写死小上限）。
- 使命完成就删，不留"已升包留档"副本——git 历史即档案，知识进 dev_plan / commit message。
