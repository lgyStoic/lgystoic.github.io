# PRD：私有收件箱 · 小红书学习文稿

> 代码：`tools/inbox.py`、`tools/xhs.py`；数据全部在私有仓库 `lgyStoic/radar-inbox`（默认，`INBOX_REPO` 可改）；工作流：`radar.yml` 第三步（收件箱）、`xhs.yml`（01:10 UTC）。公开仓库只放代码。

## 1. 目标与非目标

**目标**
- 收件箱：小红书、微信、X 这类抓不到 RSS 的内容，手机上一键投递，次日自动整理成私有的每日摘要与索引。
- 学习文稿：把当天雷达的 high / medium 条目变成「学习卡片 + 小红书草稿」初稿，供人工核对后发布。

**非目标**：不公开任何投递内容；不自动发布到小红书；不硬抓这些平台。

## 2. 约束

- 需要 `INBOX_TOKEN`（fine-grained PAT，只授权私有仓库的 Issues 与 Contents 读写）；没有则两个脚本直接跳过。
- 投递入口是私有仓库里的一个 Issue（「📥 雷达收件箱」），iOS 快捷指令往 Issue 追加评论（链接 + 可选备注）。
- 文稿标明「自动生成初稿，请人工核对事实和语气后再发布」。

## 3. 功能清单

| 功能 | 说明 |
|---|---|
| 投递 | 分享 → 快捷指令 → Issue 评论 |
| 整理 | 读取新评论 → 抓 OG 标题 / 描述（失败用备注）→ 模型写一句摘要与标签 → 写 `digest/<日期>.md/.json` → 更新 `README.md`（最近 30 条索引）→ 更新 `state.json`（进度）→ 给处理过的评论点 👍 |
| 首次运行 | 自动创建 Issue 与 README |
| 学习文稿 | 读 `radar/data/<日期>.json` 的 high / medium 前 20 条 → 每条生成 headline、takeaways、小红书草稿 → 本地 `radar/data/xhs-<日期>.md` + 私有仓库 `posts/<日期>.md` |

## 4. 数据模型（私有仓库）

`state.json`：`{issue, last_comment_id, ...}`；`digest/<日期>.json`：`[{url, title, description, note, summary, tags[], site, comment_id}]`；`posts/<日期>.md`：每条 `## headline / 原始条目 / 链接 / 学习要点 / 小红书草稿`。

## 5. 验证与排查

- `radar.yml` 日志的收件箱段：处理了几条、写了哪些文件；`INBOX_TOKEN` 缺失时打印跳过。
- `INBOX_API_BASE` 可指向本地 mock 做测试。
- `xhs.yml` 日志 `[xhs] 生成 N 条，写入 <repo>`；`RADAR_DATE` 可指定日期重跑。

## 6. 已知问题

1. 公开仓库里也会留一份 `radar/data/xhs-<日期>.md`（文稿本身不敏感，但会随雷达数据一起公开）。
2. 小红书对「引导站外」限流，草稿里的站点链接需要人工决定是否保留。
3. 收件箱摘要没有回流到公开站（「我读过的」尚未做）。

## 7. 待办

1. 「我读过的」：从收件箱摘要里挑可公开的条目，进笔记模块的阅读列表。
2. 文稿多平台版本（知乎 / 即刻）与图卡生成。
3. 投递去重（同一链接多次投递）。

## 8. 常见改动去哪改

| 想做什么 | 改哪里 |
|---|---|
| 改摘要提示词 / 标签 | `inbox.py enrich` |
| 改文稿风格、条数 | `xhs.py SYSTEM / SCHEMA`、`items[:20]` |
| 换私有仓库 | 环境变量 `INBOX_REPO` |
| 改运行时间 | `xhs.yml` cron；收件箱跟随 `radar.yml` |
