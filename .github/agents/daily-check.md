# 每日巡检手册

给自动唤醒的 agent（Claude Routine，将来也可能是 Codex）用的操作手册。目标只有一个：**让雷达 / 活动 / 收件箱这条流水线每天都健康地跑，人不用盯。**

## 0. 边界（先读）

可以自主做并合并的：
- 移除连续 3 天失败或连续 3 天 0 产出的源（`radar/sources.json`、`radar/event_sources.json`）
- 修解析 / 正则 / 时间窗口这类**有 fixture 能验证**的小 bug
- 调整关键词、权重、`title_pattern`、`exclude_pattern` 这类配置
- 补 fixture、补日志、修 README 里过期的描述

**不要**做（留 PR 不合并，或只在报告里提）：
- 改页面设计、导航、文案风格
- 加新的功能模块、改数据结构（`data/*.json` 的字段）
- 改模型选择、提示词的判断标准
- 碰 Secrets、workflow 的权限、`.github/agents/`
- 任何一次改动超过 3 个文件、或 150 行

永远不要：把 key 写进仓库；force-push；跳过 fixture 验证就合并。

## 1. 看什么

1. 最近一次 `AI 信息雷达` workflow 的日志（Actions → radar.yml → 最新 run → job logs）。关注：
   - `[radar] ✗` / `[events] ✗` 行：哪个源失败，错误是什么
   - `共 N 条新内容（共 M 条）` 里 M=0 的源：抓到了但解析出 0 条，多半是格式变了
   - `AI 失败` / `退回规则` / `finishReason`：AI 环节有没有退回
   - `Gemini 完成（模型名）`：实际用的模型；连续降级到 flash 要提
2. `radar/data/<今天>.json`：`ai` 是否为 true、`counts` 分布是否离谱（比如 90% 都是 high）
3. `radar/data/events.json`：`sources[]` 各源 count；没有日期的活动数量是否在下降
4. 定时触发有没有发生（run 的 `event` 是 `schedule`）。连续两天没有定时 run，报告里标红
5. Pages 有没有跟着部署（`GET /repos/…/deployments` 最新一条的 sha 是否等于 master）

## 2. 怎么修

- 建分支 `radar-check/YYYY-MM-DD`，改动后本地跑：
  - `python3 -c "import ast;[ast.parse(open(f).read()) for f in ('tools/radar.py','tools/events.py','tools/inbox.py','tools/build.py')]"`
  - `RADAR_FIXTURE_DIR=<fixture 目录> python3 tools/radar.py --dry-run --date 2030-01-01`（fixture 见下）
  - `python3 tools/build.py`
- fixture：仓库里没有内置 fixture 时，用 `tests/fixtures/` 目录（若不存在就建，放 2–3 个最小样例）
- 提 PR，标题以 `radar-check:` 开头，正文写清「症状 → 原因 → 改动 → 验证」。符合第 0 节「可以自主做」的直接合并；否则留着。
- 合并后手动触发一次 workflow 验证（`workflow_dispatch`），看日志确认问题消失。

## 3. 怎么报告

在 Issue「🩺 巡检日志」下追加一条评论，**不超过 8 行**，模板：

```
📅 2026-09-15 巡检
运行：schedule ✓ / 手动 ✗ ｜ AI：gemini-3.1-pro-preview ｜ 简报 N 条（必看 a）｜ 活动新增 b
问题：<一行一个，没有就写「无」>
已修：<PR 链接 + 一句话>，或「无」
待人决定：<需要 Garry 拍板的事>，或「无」
```

没有任何问题时也要留一条，只写第一、二行。不要发推送级别的通知，除非：AI 连续两天退回规则、定时连续两天没跑、或某个改动需要人拍板。
