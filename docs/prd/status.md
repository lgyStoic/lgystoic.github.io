# PRD：运行状态 · 巡检 · 兜底（/status/）

> 代码：`tools/check.py`（自检）、`tools/build.py render_status`；数据：`radar/data/last-run.json`、`radar/data/health.json`、`radar/checks/<日期>.md`；工作流：`radar.yml` 最后一步、`health.yml`；判断层手册 `.github/agents/daily-check.md`。

## 1. 目标与非目标

**目标**：让所有定时流水线每天健康地跑，人不用盯；出问题时在站内一页看清「哪一步、哪个源、为什么」。

**非目标**：不做告警推送（靠每天看状态页或 Actions 邮件）；不用模型做巡检（自检层纯规则）。

## 2. 两层结构

| 层 | 谁 | 做什么 |
|---|---|---|
| 自动层 | `check.py`（radar.yml 最后一步）、`health.yml` | 统计每个源连续失败 / 0 条天数；自动停用坏源；记录 AI 是否退回规则、定时是否触发；写当天巡检报告；当天没跑就补跑 |
| 判断层 | Claude 会话（按需） | 只处理 `health.json.needs_agent` 里的事：源改版、抽取明显错、要不要加源。边界见手册：可自主改配置与有 fixture 的小 bug；不改设计、数据结构、模型与提示词、Secrets、workflow 权限；单次 ≤3 文件 / 150 行 |

## 3. 状态页功能

| 区块 | 内容 | 标记 |
|---|---|---|
| 最近一次运行 | run 编号、触发方式（定时 / 手动 / 兜底补跑）、北京时间、Actions 链接；访问统计状态与看板链接 | `build:status-run` |
| 摘要行 | 今日简报条数与模型；活动清单条数与模型；岗位条数、来源通率、更新时间；开源贡献仓库数、任务卡数、模型、更新时间 | 同上 |
| 巡检报告 | 最近若干天 `radar/checks/*.md`，有「问题：」且非「无」的高亮 | `build:status-checks` |
| 源健康表 | 栏目（简报 / 活动 / 岗位 / 开源贡献）、源、状态（正常 / 无新内容 / 解析 0 条 / 失败 / 已停用）、新 / 总、错误或停用原因 | `build:status-sources` |

页面 `noindex`，不进 sitemap。

## 4. 规则（`check.py`）

- 连续失败 ≥ `DISABLE_AFTER`（3）天 → 在源配置写 `disabled: true` 与原因，自动停用。
- 连续 0 条 ≥ `DISABLE_ZERO_AFTER` 天 → 自动停用，原因文案提示先查 URL 参数与解析配置再考虑反爬；连续 3 天以上先写进问题列表。
- 记录 `ai_fallback`（是否退回规则）、定时是否命中（`schedule` vs 补跑）。
- 报告 ≤ 8 行：运行方式、AI 模型、简报数、活动新增、问题、待人决定。

`health.yml`：00:35 与 02:20 UTC 各查一次 `last-run.json`，当天（北京时间）没有任何运行则 `gh workflow run radar.yml -f reason=schedule_missed`。

## 5. 数据模型

`last-run.json`：`{run_id, run_number, event, sha, started_at, url}`。
`health.json`：`{sources:{"radar:<id>"|"events:<id>":{fail,zero,name,last_ok}}, ai_fallback_days?, schedule_missed_days?, needs_agent:[...]}`。

## 6. 验证与排查

- 状态页顶部「最近一次运行」的触发方式：连续出现「兜底补跑」说明 cron 槽在丢。
- `radar/data/last-run.log` 是整轮的完整日志（tee）。
- 源被自动停用后不会自动恢复：修好后手动删除 `disabled` / `disabled_reason`。

## 7. 已知问题

1. 岗位和开源贡献的失败不计入 `health.json` 的连续天数（只在状态表可见），不会自动停用。
2. 没有推送告警。
3. `needs_agent` 目前没有定时的判断层会话在消费，靠人看。

## 8. 待办

1. 岗位源纳入 `health.json` 连续失败统计与自动停用。
2. 状态页加「最近 7 天每天是否成功」的小格子。
3. 关键失败（整轮失败、AI 连续退回规则 3 天）时发一封邮件或 Issue。

## 9. 常见改动去哪改

| 想做什么 | 改哪里 |
|---|---|
| 改自动停用阈值 | `check.py` 的 `DISABLE_AFTER / DISABLE_ZERO_AFTER` |
| 改报告内容 | `check.py` 报告段 |
| 改状态页展示 | `render_status`；页面 `status/index.html` 的标记位 |
| 改兜底时间 | `health.yml` cron |
