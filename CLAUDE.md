# CLAUDE.md

先读同目录的 `AGENTS.md`（给所有 agent 的总说明），再按它读 `docs/prd/agent.md` 与要动模块的 PRD。

铁律摘要：纯静态无框架；手机 340–430px 不横向溢出（Playwright 量 scrollWidth）；`radar/data/*.json` 是公开 API 不放密钥；模型调用走 `tools/radar.py:call_llm_json` 且无 key 时退回规则；单源失败不拖垮整轮；加源先跑 probe.yml；指南用词「推荐」不写「推广」。

改完：`python3 -m pytest -q tests && python3 tools/build.py`，提交生成物；走分支 → PR squash 到 master；改了功能顺手更新对应 PRD。
