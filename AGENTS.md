# AGENTS.md

给任何接手这个仓库的 agent（Claude Code、Codex、Cursor 等）。人读的说明见 `README.md`，Claude Code 会自动读同内容的 `CLAUDE.md`。

## 这是什么

Anaxagore（lgystoic.github.io）：跑在 GitHub Pages + Actions 上的纯静态个人平台。模块：笔记、上手指南、每日 AI 雷达、专题追踪（视频生成模型 / 世界模型）、活动、岗位、开源贡献路线、状态页；另有写入私有仓库 `lgyStoic/radar-inbox` 的收件箱与小红书文稿（每日学习卡片 + 周一岗位精选）。

## 开始任何任务前

1. 读 `docs/prd/agent.md`：不变量、仓库地图、命令、发布流程、模块速查、常见任务步骤。
2. 读要动的模块的 PRD：`docs/prd/<模块>.md`（索引 `docs/prd/README.md`）。改了功能顺手更新对应 PRD 与 `agent.md` 的相关行。

## 铁律

- 纯静态、无框架；页面不加载第三方脚本（访问统计 GoatCounter 与评论 giscus 除外）。
- 手机 340–430px 不横向溢出：用 Playwright 量 `scrollWidth`（`tools/check_mobile.py`），不要信桌面 Chrome 缩窄窗口。
- `radar/data/*.json` 是公开 API：不放密钥、不放私密内容。私密只进 `radar-inbox`。
- 模型调用一律走 `tools/radar.py:call_llm_json`，无 key 时退回规则；单个源失败不能拖垮整轮。
- 专题追踪的条目只认带日期的源；专题关键词宁缺毋滥（泛词要带版本或机构）。
- 加雷达源前先跑探针（Actions「源探针」`probe.yml` 或 `python3 tools/probe.py <url>`），不要凭记忆写 URL；趋势类源必须带创建日期；X（Twitter）从 Actions 抓不到，人物动态用 Bluesky RSS。
- 指南用词写「推荐」不写「推广」；无免责声明、无地址生成器。
- 不把模型型号写进 commit / PR；不把 key 写进仓库。

## 改完怎么交

```
python3 -m pytest -q tests && python3 tools/build.py
```
提交生成物；走分支 → PR squash 到 `master`；合并后把工作分支重置到 `origin/master`。需要数据的改动：手动触发对应 workflow，读 job 日志验证，再向站长汇报结论（站长手机看，只要决定、坏了、里程碑）。

## 相关仓库

- `lgyStoic/radar-inbox`（私有）：收件箱、小红书文稿与封面、发布队列技能。它自己有 `AGENTS.md`。
- `projects/`：外部开源贡献项目的浅克隆 submodule；从这里进入 fork 开发，主仓库只提交 submodule 指针。流程见 `projects/README.md`。
