# CLAUDE.md

这是 Anaxagore（lgystoic.github.io）的仓库：一个跑在 GitHub Pages + Actions 上的纯静态个人平台。

开始任何任务前先读：
1. `docs/prd/agent.md` — 不变量、仓库地图、命令、发布流程、模块速查、常见任务步骤。
2. 要动的模块的 PRD：`docs/prd/<模块>.md`（索引在 `docs/prd/README.md`）。

铁律摘要（细节见 agent.md）：纯静态无框架；手机 340–430px 不横向溢出（Playwright 量 scrollWidth）；`radar/data/*.json` 是公开 API 不放密钥；模型调用走 `tools/radar.py:call_llm_json` 且无 key 时退回规则；单源失败不拖垮整轮；指南用词「推荐」不写「推广」。

改完：`python3 -m pytest -q tests && python3 tools/build.py`，提交生成物；走分支 → PR squash 到 master；改了功能顺手更新对应 PRD。
