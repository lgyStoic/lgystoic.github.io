# PRD：私有收件箱

> 代码：`tools/inbox.py`；数据全部在私有仓库 `lgyStoic/radar-inbox`（默认，`INBOX_REPO` 可改）；工作流：`radar.yml` 第三步。公开仓库只放代码。小红书学习文稿与封面图另见 [xhs.md](xhs.md)。

## 1. 目标与非目标

**目标**
- 收件箱：小红书、微信、X 这类抓不到 RSS 的内容，手机上一键投递，次日自动整理成私有的每日摘要与索引。
- 学习文稿（见 xhs.md）：同一私有仓库的 `posts/`。

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

## 4. 数据模型（私有仓库）

`state.json`：`{issue, last_comment_id, ...}`；`digest/<日期>.json`：`[{url, title, description, note, summary, tags[], site, comment_id}]`。`posts/`（`cards/`、`jobs/`、`README.md` 索引）归 xhs.md。

## 5. 验证与排查

- `radar.yml` 日志的收件箱段：处理了几条、写了哪些文件；`INBOX_TOKEN` 缺失时打印跳过。
- `INBOX_API_BASE` 可指向本地 mock 做测试。

## 6. 已知问题

1. 收件箱摘要没有回流到公开站（「我读过的」尚未做）。

## 7. 待办

1. 「我读过的」：从收件箱摘要里挑可公开的条目，进笔记模块的阅读列表。
2. 投递去重（同一链接多次投递）。

## 8. 常见改动去哪改

| 想做什么 | 改哪里 |
|---|---|
| 改摘要提示词 / 标签 | `inbox.py enrich` |
| 换私有仓库 | 环境变量 `INBOX_REPO` |
| 改运行时间 | 收件箱跟随 `radar.yml`；文稿见 xhs.md |
