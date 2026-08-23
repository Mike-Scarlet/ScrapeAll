# 工作规矩（硬约束）

> 给协作者 / AI 代理的行为边界。违反任何一条都属于事故，先停再做。
> 当前进度速览见 `dev_plan/scrape_status.md`。

## 行为安全（最高优先级）

1. **批量操作必须先报数量、经用户同意才能跑。** 任何会触碰多条链接的运行——collect / fetch / 探活 / 下载 / 转存，**包括只读探活**——都算批量。单链接验证例外，但验证脚本必须写死小上限（≤6 条），禁止"扫到找到为止"式的无上限循环。
2. **配额和流量是真实成本。** 验证优先复用已知小文件；幂等检查放在点击/请求**之前**（本地已有就不点按钮，0 流量）；大文件/大列表只验证"点击 → 下载事件 → 立刻 cancel"。
3. 杀自动化 Chrome 前，先确认目标进程挂的是 `browser_session` profile（自动化实例），**不能误杀用户自己的浏览器**。

## 下载基建约定（scrape_all/downloader/）

4. **所有网络取回走浏览器页**：真实 Chrome 指纹 + `browser_session/` 持久 profile 登录态 + `DOWNLOADER_PROXY_SERVER` 代理。不用 python http 客户端；pixeldrain 这类站点走"开页面 → 读渲染结果 → 点页面上的按钮"，**不走裸 API 端点**（已踩坑：`/api/file/{id}` 是文件本体不是元信息）。
5. **并发默认 1 串行**（`DOWNLOADER_CONCURRENCY`，引擎级信号量 + 同 origin 页级锁）。调整需用户同意。
6. **adapter 是单链接契约**：`probe` / `download` 各吃一个 URL，可中断可重跑（幂等靠"已存在跳过"）。批量遍历属于编排层，编排层动手前回到规矩 1。

## 落盘

7. topic 级目录 `{topic_id}_{标题slug}/`，脚本与视频同目录（播放器按同名匹配）。文件名一律过 `sanitize_filename`：非法字符替换 `_`、Windows 保留名（CON/COM1…）加前缀、超长截断保扩展名。

## 流程

8. **逐家 host 做完单链接可信的 adapter，再谈批量编排。** 接入顺序：catbox ✅ → eros uploads ✅ → pixeldrain（页面流已实现，剩最终验证）→ gofile → mega → gdrive → workupload。
9. commit / push 由用户明确要求才做。
