# agent.md — 给 agent 看的站点说明（压缩版）

读法：先读本文件，再读要动的模块 PRD（同目录）。人读版总览在 `index.html`（站内 `/docs/prd/`）。改功能后更新对应 PRD 与本文件的相关行。

## 0. 不变量（违反任何一条即回退）

- 纯静态；无框架、无构建依赖；页面不加载第三方脚本（例外：GoatCounter `gc.zgo.at`、giscus）。
- 页面在 340/360/390/430px 视口 `document.documentElement.scrollWidth <= 视口宽`。验证用 `python3 tools/check_mobile.py <页面…>`（Playwright；`--all` 全站），不用桌面 Chrome 窄窗口截图。
- `radar/data/*.json` 公开 → 无密钥、无私密内容。私密只进 `lgyStoic/radar-inbox`。
- 所有模型调用经 `tools/radar.py:call_llm_json`；没有 key 必须退回规则而不是失败。
- 单个源/仓库失败不得让整轮失败；失败沿用上次结果并标 `stale`/写 `sources[].error`。
- 推荐位用词「推荐」，禁「推广」与免责声明；未亲测内容标「未亲测」；不编造价格、不做地址生成器。
- 提交信息、PR、页面文字用中文；代码标识符保留原文。提交/PR 不写模型名。

## 1. 仓库地图

```
site.json                 模块注册表（nav、modules[]、analytics、comments、seo.verification）
tools/build.py            全站构建：注入 <!-- build:NAME --> 块、sitemap、feed、状态页、指南处理
tools/radar.py            雷达 + 共用 LLM 层（call_llm_json/call_gemini_json/_gemini_once）
tools/events.py           活动清单
tools/jobs.py             岗位主抓取；import_liepin.py / import_ats_jobs.py / jobbuddy_enrich.py / jobs_ai.py 适配器
tools/contributions.py    开源贡献：采集→五章→任务卡→校验→渲染（含 arch_svg/flow_svg）
tools/inbox.py tools/xhs.py 私有收件箱、小红书文稿 + 封面卡片（写私有仓库 digest/ posts/）
tools/check.py            自检（源健康、自动停用、巡检报告）
tools/prd_index.py        生成 docs/prd/index.html
tools/probe.py            源探针：试抓 URL 打印状态/条数（Actions 里用 probe.yml）
tools/check_mobile.py     Playwright 手机宽度溢出检查
tools/indexnow.py         radar.yml 推送后把当天变化页面推给 Bing IndexNow（密钥 site.json.seo.indexnow_key + 根目录 <key>.txt）
radar/{sources,event_sources,job_sources,contribution_repos,ats_companies}.json  配置
radar/data/               数据（<日期>.json, events.json, jobs.json, contributions.json, health.json, last-run.json, seen.json）
radar/checks/*.md         巡检报告
notes/notes.json          笔记索引；templates/note/ 模板
guides/{guides,links}.json 指南篇目、推荐链接注册表
.github/workflows/{radar,health,jobs,contributions,xhs}.yml
.github/agents/daily-check.md  判断层手册（边界）
docs/prd/*.md             本目录
docs/tasks/*.md           进行中的任务说明（自包含，先读 agent.md 再读它）
tests/test_jobs.py        唯一单测
```

## 2. 命令

```bash
python3 tools/build.py                 # 幂等全站重建；改渲染器后必须跑并提交产物
python3 -m pytest -q tests             # 5 个单测
python3 tools/radar.py --dry-run       # RADAR_FIXTURE_DIR=tests/fixtures 可离线
python3 tools/events.py --dry-run
python3 tools/contributions.py --list [--focus] | --only owner/repo --out f.json | --merge dir [--scope focus]
python3 tools/prd_index.py             # 重生成人读版总览
python3 tools/check_mobile.py --all    # 手机宽度溢出检查（需 pip install playwright）
```

环境限制（Claude Code 沙箱）：能访问 api.github.com（仅本仓库）、raw.githubusercontent.com、PyPI；访问不到国内招聘站、hn.algolia.com、Azure blob（Actions 产物）。这类问题只能通过修改后在 Actions 跑一次、读日志验证。

## 3. 发布流程

1. 在 `claude/personal-page-design-h84ilf` 分支开发（先 `git checkout -B <branch> origin/master`）。
2. `python3 -m pytest -q tests && python3 tools/build.py`；如改了页面/CSS，跑一次 Playwright 溢出检查。
3. 提交（中文标题 + 要点），push，开 PR，squash 合并到 master；合并后把分支重置到 origin/master。
4. 需要数据的改动：手动触发对应 workflow（`actions_run_trigger`），用 `api.github.com/.../runs` 轮询，读 `get_job_logs` 验证。

工作流通用：cron 不在整点；`concurrency` 按工作流；机器人推送被拒 → 保留数据文件 → `reset --hard origin/master` → `build.py` → 再推，三次。改这段要四个工作流同步。

AI 模型：`call_llm_json` 走 Claude（有 key）否则 Gemini；模型名由仓库变量 `vars.GEMINI_MODEL` / `vars.GEMINI_FALLBACK_MODEL` 覆盖，默认首选 `gemini-flash-latest`（→3.8 Flash），备选 `gemini-pro-latest`（→3.1 Pro）；可用模型清单看 site.md §5 或跑 `xhs.yml list_models`。日志出现 `finishReason=MAX_TOKENS` → 调大 `GEMINI_MAX_OUTPUT_TOKENS`。

## 4. 模块速查

| 模块 | 入口 | 配置 | 数据 | 工作流 | 关键函数 | 日志标签 |
|---|---|---|---|---|---|---|
| 雷达 | `radar.py main` | `radar/sources.json`（site/categories/rules/sources；源字段 kind,json,urls(镜像),link_host,weight,window_hours,title_pattern,require_topic,disabled；X 抓不到，人物走 Bluesky RSS；加源前跑 probe.yml） | `radar/data/<日期>.json`, `seen.json` | radar.yml 23:50/00:20/02:05 UTC + guard | `collect, score_item, dedupe_titles, enrich_with_ai, finalize` | `[radar]`, `[radar-ai]` |
| 活动 | `events.py main` | `event_sources.json`（site.cities/keep_past_days/max_*；kind rss,json,ics,page,yaml,wechat） | `events.json` | radar.yml 第二步 | `collect, fetch_detail, enrich_events, to_event` | `[events]`, `[events-ai]` |
| 岗位 | `jobs.py main` → 适配器 → `jobs_ai.py` | `job_sources.json`（profile.directions/title_terms/exclude_title/max_per_company(_cn)；sources kind 12 种；disabled+disabled_reason；search_links） | `jobs.json` | jobs.yml 00:35 UTC | `match, region_of, limit_jobs, fetch_source(feishu_csrf, feishu_site_path), collect` | `源失败`, `岗位：N；来源成功`, `猎聘：`, `jobs-ai：` |
| 开源贡献 | `contributions.py main` | `contribution_repos.json`（str 或 {repo,focus,young}） | `contributions.json` | contributions.yml 周一/周四 01:20 UTC；inputs scope, reuse_run_id | `collect_repo, run_analysis, task_prompt, valid_tasks, merge_tasks, scrub_channels, assemble, render, arch_svg, flow_svg` | `[contribution-<owner>-<repo>-<stage>]`, `丢弃…`, `降级到` |
| 收件箱 | `inbox.py` | env INBOX_TOKEN, INBOX_REPO | 私有仓库 digest/, state.json | radar.yml 第三步 | `fetch_comments, enrich, render_day_md` | `[inbox]` |
| 小红书文稿 | `xhs.py run_cards / run_jobs(--jobs)` | env XHS_IMAGES(4), XHS_JOBS_REGION, GEMINI_IMAGE_MODEL；xhs.yml inputs date, images, mode, jobs_region, preview, list_models | 私有仓库 posts/cards/<日期>.md+/<id>.jpg、posts/jobs/<日期>.md+/cover.jpg、posts/README.md（本地 radar/data/xhs* 已 gitignore） | xhs.yml 01:10 UTC 每日卡片；周一 01:40 UTC 岗位周报 | `pick_jobs, clean_post, gemini_image, card_html, render_cards, publish, update_index` | `[xhs] 配图：`, `[xhs] 封面图 N 张`, `[xhs] 岗位周报`, `[xhs] 标题超 20 字` |
| 巡检 | `check.py` | `DISABLE_AFTER=3`, `DISABLE_ZERO_AFTER` | `health.json`, `radar/checks/*.md`, `last-run.json` | radar.yml 末步；health.yml 00:35/02:20 UTC | `main` | 报告 ≤8 行 |
| 笔记 | `build.py` | `notes/notes.json` | — | — | `render_latest, render_archive, render_tag_filters` | — |
| 指南 | `build.py build_guides` | `guides/guides.json`, `guides/links.json` | — | — | `apply_affiliate_links, apply_guide_support, render_guide_jsonld` | `guides/<id>: 推荐位 N 个已填` |
| GEO | `build.py write_llms_txt / render_*_jsonld` | `robots.txt` | `llms.txt`、各页 JSON-LD | — | `render_note_jsonld, render_radar_jsonld, render_events_jsonld` | 构建后所有 ld+json 必须能 json.loads |
| 状态页 | `build.py render_status` | — | 读所有 data | — | `render_status.add_rows`（简报/活动/岗位/开源贡献） | — |

## 5. 开源贡献硬规则（改前先读 contributions.md §6）

`valid_tasks` 顺序：Issue 真实 → compute_class∈{CPU,Mac,Colab T4} → 硬件绑定词丢 → CPU/Mac 卡命中 `GPU_ONLY` 丢 → `local_repro`<8 字丢 → `ENV_ONLY` 丢(help wanted 降 low) → 有 assignee/open PR 标 `review_only`，全库 ≤`REVIEW_CAP=2` → 上限 focus 12 / 普通 6，提案 ≤5。不满 focus 8 / 普通 4 时 `TOPUP_SCHEMA` 补卡一次。`diagram.layers[].modules` 用逗号分隔且必须与 `modules[].module` 一字不差；节点名不能含 `/ , ; 、`。

## 6. 常见任务 → 步骤

- **加雷达/活动源**：改对应 json → `--dry-run` 看该源条数 → 提交。停用写 `disabled:true, disabled_reason`。
- **加岗位源**：`job_sources.json.sources` 加项（kind 已有的直接用；新 kind 在 `fetch_source` 加分支）→ 沙箱无法访问则直接开 PR 合并后 `actions_run_trigger jobs.yml` → 读日志。
- **加贡献仓库**：`contribution_repos.json` → 手动触发 contributions.yml（scope=all 或把仓库标 focus 用 scope=focus）。
- **改渲染不重跑 Gemini**：改代码 → 合并 → 触发 contributions.yml `reuse_run_id=<最近成功 run>`（产物 3 天内有效）。
- **改页面/CSS**：`build.py` → Playwright 四宽度 scrollWidth → 提交生成物。
- **排查某天为什么没跑**：状态页「最近一次运行」触发方式；`last-run.json`；health.yml 是否补跑；`radar/data/last-run.log`。
- **新页面类型**：写 `render_<x>_jsonld`，head 放 `<!-- build:<x>-jsonld -->`，`main()` inject；实体名只用 Anaxagore / lgystoic.github.io（见 geo.md）。
- **新模块**：`site.json.modules` 加项 → 页面放 `build:header/site-name/analytics` 标记 → `module_status` 加状态行 → 脚本进 `tools/`，工作流复制推送策略 → 写 `docs/prd/<模块>.md` → 更新本文件与 `README.md`。

## 7. 禁止

- 不改 `radar/data/*.json` 字段结构而不同步 `build.py` 渲染与 PRD。
- 不在页面 HTML 手改由 build 注入的块（会被覆盖）。
- 不 rebase / force-push master；不把 key 写进仓库；不绕过 `valid_tasks` 让 GPU 任务上页面。
- 不在指南页写「推广」「含推广链接」；不加地址生成器。
