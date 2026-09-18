# 每日巡检手册

目标只有一个：**让雷达 / 活动 / 收件箱这条流水线每天都健康地跑，人不用盯。**

巡检分两层，先分清谁干什么：

| 层 | 谁 | 干什么 | 依赖 |
|---|---|---|---|
| **自动层** | GitHub Actions（`tools/check.py`，radar.yml 最后一步；`health.yml` 每天早上两次兜底补跑） | 统计每个源连续失败 / 0 条天数；连续失败 ≥ 3 天自动停用；记录 AI 是否退回规则、定时是否触发；写当天报告 `radar/checks/<日期>.md`；把需要判断的事列进 `radar/data/health.json` 的 `needs_agent` | 只依赖 GitHub，不依赖任何 Claude 会话 |
| **判断层** | agent（Claude 会话，按需或定时；将来也可能是 Codex） | 只处理 `needs_agent` 里的事：源改版要改解析、抽取明显错、要不要加/换源 | 本手册 |

自动层每天都在；判断层只在 `health.json` 的 `needs_agent` 非空时才有事做，空的话直接回复「无事」结束。

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

## 前提：你可能没有 GitHub API 权限

自动唤醒的会话通常**没有** GitHub MCP 工具，也没有 token。所以整个流程只靠 `git`：
- 读：`git pull`，看仓库里 workflow 自己留下的文件——`radar/data/last-run.json`（运行元数据：run_id、event、时间、链接）、`radar/data/last-run.log`（三个脚本的完整日志）、`radar/data/<今天>.json`、`radar/data/events.json`
- 写：改好的东西直接 commit + push；报告写成文件 `radar/checks/YYYY-MM-DD.md` 一起提交，`/status/` 页会把它渲染出来
- 触发一次运行：`date -u > radar/trigger && git add radar/trigger && git commit -m "radar-check: trigger run" && git push`，然后每 20 秒 `git pull` 一次，直到 `last-run.json` 的 `started_at` 变新、且 `last-run.log` 末尾出现 `已生成`
- 如果会话里恰好有 GitHub MCP 工具，可以用它看 Actions 页面和开 PR，但不要依赖

## 1. 看什么

先看 `radar/data/health.json`：`needs_agent` 为空且今天的 `radar/checks/<日期>.md` 里「问题：无」，就不用再往下看。否则：

1. `radar/data/last-run.log`（最近一次运行的完整日志）。关注：
   - `[radar] ✗` / `[events] ✗` 行：哪个源失败，错误是什么
   - `共 N 条新内容（共 M 条）` 里 M=0 的源：抓到了但解析出 0 条，多半是格式变了
   - `AI 失败` / `退回规则` / `finishReason`：AI 环节有没有退回
   - `Gemini 完成（模型名）`：实际用的模型；连续降级到 flash 要提
2. `radar/data/<今天>.json`：`ai` 是否为 true、`counts` 分布是否离谱（比如 90% 都是 high）
3. `radar/data/events.json`：`sources[]` 各源 count；没有日期的活动数量是否在下降
4. 定时触发有没有发生：`last-run.json` 的 `event` 应为 `schedule`、`started_at` 是今天。连续两天不是，报告里标红
5. Pages 有没有跟着部署：`curl -sI https://lgystoic.github.io/radar/` 能通就看页面上的日期是否是今天；沙箱访问不到外网时跳过这项并注明

## 2. 怎么修

- 在 master 上直接改（没有 API 就开不了 PR；符合第 0 节「可以自主做」的改动直接 commit 到 master，commit 信息以 `radar-check:` 开头并写清症状→原因→改动→验证）。**超出边界的**改动推到分支 `radar-check/YYYY-MM-DD-<slug>`，不合并，在报告里给分支名。
- 改动后本地跑：
  - `python3 -c "import ast;[ast.parse(open(f).read()) for f in ('tools/radar.py','tools/events.py','tools/inbox.py','tools/build.py')]"`
  - `RADAR_FIXTURE_DIR=<fixture 目录> python3 tools/radar.py --dry-run --date 2030-01-01`（fixture 见下）
  - `python3 tools/build.py`
- fixture 在 `tests/fixtures/`；新问题先补一个最小样例再修
- push 到 master 后，用 `radar/trigger` 触发一次运行（见「前提」），等日志回来确认问题消失。

## 3. 怎么报告

自动层已经写了当天的 `radar/checks/YYYY-MM-DD.md`。agent 有动作时在文件末尾**追加**一行 `agent：<做了什么 / 分支名>`，和代码改动一起 commit、push。自动报告的模板：

```
📅 2026-09-15 巡检
运行：schedule ✓ / 手动 ✗ ｜ AI：gemini-3.1-pro-preview ｜ 简报 N 条（必看 a）｜ 活动新增 b
问题：<一行一个，没有就写「无」>
已修：<PR 链接 + 一句话>，或「无」
待人决定：<需要 Anaxagore 拍板的事>，或「无」
```

没有任何问题时也要留一条，只写第一、二行。会话的最终回复不超过 3 行，只有「AI 连续两天退回规则」「定时连续两天没跑」「需要 Anaxagore 拍板」三种情况才以「⚠️ 需要关注」开头——这一行会推送到手机。

`/status/` 页面（`tools/build.py` 渲染）会展示最近 14 天的报告和最近一次运行的源健康表，Anaxagore 在手机上看的是那里。
