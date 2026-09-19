# PRD：开源贡献路线（/radar/contributions/）

> 状态：已上线，持续迭代。最后整理：2026-09-19。
> 代码：`tools/contributions.py`（采集 / Gemini / 校验 / 渲染全在这一个文件）、`.github/workflows/contributions.yml`、`radar/contribution_repos.json`。
> 数据：`radar/data/contributions.json`。页面：`radar/contributions/index.html` 与每个仓库一个子目录。

---

## 1. 目标与非目标

**目标**：让站长（资深 GPU kernel / 训练性能工程师，目前只有一台 16GB Apple Silicon MacBook Air，没有 GPU）在不读完整个仓库的情况下，知道每个候选开源项目

1. 是什么、架构什么样、在 Mac 上怎么跑起来；
2. 维护者是谁、社区怎么运作、现在最缺什么；
3. 该从哪切入、第一批 PR 做什么、30 / 60 / 90 天怎么走；
4. 今晚就能开工的具体任务是哪几张，怎么得体地认领。

最终指向：成为一两个重点仓库的长期维护者。

**非目标**

- 不做通用的 GitHub Issue 聚合器；只服务这一份候选人画像（`PROFILE` 常量）。
- 不替用户提交 PR、不替用户在 Issue 下留言；页面只给出可复制的英文留言草稿。
- 不推荐需要真机 GPU 才能复现或验证的任务（Colab 免费 T4 只做几十分钟的最终确认）。
- 不做用户登录、收藏、进度同步；页面纯静态。

## 2. 用户与硬约束

| 约束 | 含义 | 在代码里的体现 |
|---|---|---|
| 无 GPU | 任务必须能在 CPU / Apple Silicon 上开发、复现、验证 | `PROFILE`、任务卡规则 3 / 11、`GPU_ONLY` 正则、`compute_class` 白名单 |
| 手机为主 | 所有页面 340–430px 宽不能横向溢出，图要能读 | `.wrap{overflow-wrap:anywhere}`、架构图容器可横滑、流程图竖排 |
| 得体介入 | 有人认领或有 open PR 的 Issue 不能推荐去做 | `is_claimed`、`review_only`、`REVIEW_CAP=2` |
| 只依据证据 | 不编造文件、类、频道、bug | 章节提示词「不确定写需验证」、`scrub_channels`、first_prs 不得假设 bug |
| 无外部 JS | 页面不加载第三方脚本（站点统计除外） | 架构图是 build 时生成的内嵌 SVG |

## 3. 页面功能清单

### 3.1 首页 `/radar/contributions/`

| 功能 | 说明 | 代码 |
|---|---|---|
| 状态行 | 更新时间 + 实际模型（如有阶段降级会写明「第 X 章 / 任务卡：模型名」） | `render()`、`summarize_global_model` |
| 本周先做这三个 | 从全部任务卡里挑 3 张：无人认领、无 open PR；优先级高、难度低、CPU/Mac、能用上 kernel 专长的排前；重点仓库加权；三张来自三个不同仓库 | `render()` 里的 `picks` |
| 仓库卡片网格 | 每个仓库：候选任务数、项目一句话定位、长期负责方向、Star、最近推送、前 3 张卡标题、进入详情链接 | `render()` |
| 站点接入 | 首页卡片、sitemap、状态页健康表由 `build.py` 汇总 | `build.py` 1137–1173 行附近 |

### 3.2 仓库详情页 `/radar/contributions/<owner>--<repo>/`

顶部 hero：仓库名、契合度一句话、当前方向、Star / Fork / 任务数 / 实际模型、更新时间、是否沿用旧结果（stale）。

七章结构（`analysis_html` + `detail_page`）：

| 章 | 内容 | 数据字段 |
|---|---|---|
| 一、项目定位 | 概览（400–600 字）、解决的问题与用户、同类项目差别、核心能力表（能力 / 在哪 / 成熟度，成熟度以 README 自述为准）、阶段、技术栈、规模数字 | `analysis.positioning` |
| 二、架构与代码地图 | 分层描述；**架构图**（分层泳道 + 模块方框 + 依赖箭头，回流虚线，可横滑）；模块表（路径 / 职责 / 入口 / 依赖 / 规模）；目录树（按文件数）；一次调用的数据流文字 + **流程图**（竖排编号）；关键类型与函数；扩展点；最近在动的地方（提交热点）；建议阅读顺序 | `analysis.codemap`（`diagram`、`flow` 为图的结构化数据） |
| 三、本地跑起来 | 无 GPU Mac 上的安装命令；哪些路径能真跑 / 只能读 / 需 Colab；最小可运行命令；测试套件；调试技巧；CI 会卡什么；常见坑 | `analysis.runbook` |
| 四、维护者与社区 | 提交 / Release 节奏；主要维护者（角色 + 依据）；贡献流程；Review 风格；渠道（只允许证据里出现过的链接）；得体 / 不得体；维护者现在最想要什么 | `analysis.community` |
| 五、切入方案 | 缺口表（缺口 / 依据 / 为什么是你）；长期负责的方向及理由；30 / 60 / 90 天可勾选清单；第一批 PR（题目 / 范围 / 为什么安全）；站住脚的信号；风险与对策 | `analysis.entry` |
| 六、怎么介入 | 仓库级介入规范 3–5 条；社区入口链接；建议顺序；成为长期维护者的路径 | `how_to_engage`、`recommended_order`、`maintainer_path` |
| 七、任务卡 | 见 3.3 | `tasks[]` |

### 3.3 任务卡（每张）

| 区块 | 字段 |
|---|---|
| 头部 | 优先级（优先 / 可选 / 候补）、难度、算力等级（CPU / Mac / Colab T4）、工时估计、中文标题、来源 Issue 链接（提案卡为 commit 或仓库链接） |
| 徽章 | 无人认领 / 已指派 X / 已有 PR #N / 提案·需先开 Issue；评论数；标签；最近更新日期 |
| 正文 | 用到的专长、目标、为什么值得长期做、怎么介入、第一个 PR 的边界、第一步、**本机怎么复现 / 验证**（`local_repro`） |
| 认领留言 | 英文、≤120 词、一键复制（提案卡则是英文 Issue 草稿，第一行是标题） |
| 折叠区 | 实施方案步骤、可能涉及的目录或文件、验收方式、开工前要问维护者的问题、风险 |

卡片类型：`kind=issue`（绑定真实 open Issue）与 `kind=proposal`（仅 `young=true` 的仓库，依据 README / commits 提议，最多 5 张）。

## 4. 数据管线

### 4.1 工作流 `.github/workflows/contributions.yml`

```
plan ──► analyze (matrix, 每仓库一个 job, max-parallel 7) ──► merge
```

| 触发 | 范围 |
|---|---|
| 周一 01:20 UTC | 全部仓库（14 个，约 15 分钟） |
| 周四 01:20 UTC | 只跑 `focus: true` 的重点仓库，其余原样保留 |
| 手动 `scope=all/focus` | 同上 |
| 手动 `reuse_run_id=<run id>` | 不调用 Gemini，直接用那次 run 上传的产物重新合并、渲染（改渲染器 / 合并失败后重做用；产物保留 3 天） |

- analyze 环境：`GEMINI_MODEL=gemini-flash-latest`、`GEMINI_FALLBACK_MODEL=gemini-pro-latest`（均可用仓库变量覆盖；2026-09-19 起与全站一致首选 Flash）、`GEMINI_MAX_OUTPUT_TOKENS=32768`、`GEMINI_TIMEOUT=600`、`GEMINI_PRIMARY_RETRIES=2`、job 超时 45 分钟。
- merge：下载 `contrib-*` 产物 → `--merge results --scope <scope>` → `build.py` → 提交。推送被拒时保留 `contributions.json`、回到最新 master 重新渲染，最多三次（不 rebase 生成物）。
- `merge` 必须 `needs: [plan, analyze]`，否则拿不到 plan 的 outputs。

### 4.2 单仓库流程 `analyze_repo`

1. `collect_repo`：仓库元数据、README（重点仓库 20k 字）、CONTRIBUTING、open Issue（重点 100 条 + good first issue / help wanted + 7 组方向关键词搜索；普通 30 条）、每个 Issue 的时间线关联 PR（重点 120 条、普通 40 条，没查到的不进候选池）、open PR 10 条、Release 3 个、commit 12 个、递归目录树摘要、提交热点、关键文件（pyproject / CMakeLists / AGENTS.md…）、10 个关键源码文件开头 3500 字。
2. `run_analysis`：五章**顺序**生成，后一章能看到前面章节的结论（`_shrink` 压到 1200 字）。任一章失败整个仓库失败，沿用上次结果并标 stale。
3. 任务卡：`task_prompt` 把「优先候选池」（无人认领、无 open PR，按更新时间新→旧，前 45 条保留正文）放在提示词最前面，已有人做的只留标题；输出走 `REPO_SCHEMA`。
4. `valid_tasks` 硬校验（见第 6 节）。
5. 补卡：重点仓库不满 8 张、普通不满 4 张时，用剩余候选池再调一次（`TOPUP_SCHEMA`），`merge_tasks` 去重合并。
6. `scrub_channels` 去掉证据里没有的 `#频道名`。
7. 记录每阶段实际模型（`models` 字典），`summarize_models` 生成页面上的模型一句话。

### 4.3 Gemini 调用（`tools/radar.py`）

- `call_llm_json(system, user, schema, label)`：有 `ANTHROPIC_API_KEY` 先走 Claude，否则 Gemini；结构化 JSON 输出。
- 瞬时错误（超时 / 429 / 5xx）先重试首选模型再降级；解析失败或输出被截断直接降级。`LAST_MODEL_USED` 记录实际模型版本。
- 日志前缀：`[contribution-<owner>-<repo>-<阶段>]`，阶段为 `positioning / codemap / runbook / community / entry / tasks / tasks-topup`。

## 5. 数据模型 `radar/data/contributions.json`

```
{ updated, model, failures:[{repo,error}],
  repos:[{
    repo, fit, current_direction, recommended_order[], maintainer_path[], how_to_engage[],
    model, models:{positioning,codemap,runbook,community,entry,tasks,tasks-topup?},
    stale?: true,
    analysis:{ positioning{overview,problem,users,landscape[],stage,capabilities[],stack[],numbers},
               codemap{layers,modules[],data_flow,key_types[],extension_points[],hotspots[],reading_order[],
                       diagram{layers[{name,modules}],edges[{from,to,label}],caption}, flow[{step,component,path}]},
               runbook{install[],no_gpu_paths,smoke_test[],test_suite,debug_tips[],ci,pitfalls[]},
               community{cadence,people[],process,review_style,channels[],etiquette[],what_they_want[]},
               entry{gaps[],ownership_target,why_this_target,phase_30[],phase_60[],phase_90[],first_prs[],signals_of_progress[],risks[]} },
    evidence:{ repo,url,description,stars,forks,open_issues,pushed_at,default_branch,focus,young,
               tree,commit_hotspots,contributing,community[],root_paths[],issues[],pulls[],releases[],commits[] },
    tasks:[{ title, kind, source_url, source_number, source_title, priority, difficulty, compute, compute_class,
             time_estimate, skill_fit, goal, why_core, engagement, pr_scope, first_action, local_repro,
             implementation_steps[], likely_paths[], validation[], questions[], risks[], claim_comment,
             review_only, issue_status{assignees[],comments,labels[],updated_at,created_at,open_prs[],proposal?} }]
  }] }
```

`evidence` 里不保存 README、关键文件、源码片段和完整代码路径（太大）。这个文件是公开 API，别放密钥或私有信息。

## 6. 硬校验规则（`valid_tasks`）

按顺序，任一不满足即丢弃并在日志打印原因：

1. `source_url` / `source_number` 必须逐字来自输入的 Issue（提案卡来自 commits 或仓库 URL，且仓库 `young=true`）。
2. `compute_class` ∈ {CPU, Mac, Colab T4}。
3. 标题或算力描述含 SM 型号 / Hopper / Blackwell / H100 / A100 / 多卡 / NVLink → 丢。
4. CPU / Mac 卡的实施步骤、验证、复现、第一步里出现 `GPU_ONLY`（memory saver、release/resume_memory_occupation、LD_PRELOAD、CUDA Graph、NCCL、nvidia-smi、cudaMalloc、torch.cuda.、CUDA 流）→ 丢。
5. CPU / Mac 卡 `local_repro` 少于 8 个字符 → 丢。
6. 标题 / Issue 标题 / 目标匹配 `ENV_ONLY`（Homebrew、install.sh、xattr、Gatekeeper、pip 依赖、conda…）→ 丢；Issue 标了 help wanted 的保留但降为 low。
7. 有 assignee 或 open PR 的 Issue → `review_only=true`，全库最多 `REVIEW_CAP=2` 张，按优先级留。
8. Issue 卡上限：重点 12 张、普通 6 张；提案卡最多 5 张。

## 7. 渲染

| 函数 | 产物 |
|---|---|
| `render()` | 首页正文（注入 `radar/contributions/index.html` 的 `<!-- build:contributions -->`） |
| `write_detail_pages` / `detail_page` | 每仓库 `radar/contributions/<slug>/index.html`，`slug = owner--repo` 小写 |
| `analysis_html` | 目录 + 一至五章 |
| `arch_svg(diagram, modules)` | 架构图：层内按上一层邻居重心排序；紧挨的同层模块画直箭头；标签避开方框与画布边缘；模块名对不上模块表的边不画；层数 < 2 不出图 |
| `flow_svg(flow)` | 流程图：≥3 步才出图 |
| `task_card` / `status_badges` | 任务卡 |
| `esc` | 转义后还原 `**粗体**` 和 `` `代码` `` |

样式：详情页私有样式写在 `detail_page` 的 `<style>` 里（`.d-*` 为图的类名）；首页卡片样式在 `render()` 输出的内联样式与 `site.css` 的 `.picks` / `.pick-list`。全站规则（`.wrap`、`.table-wrap`、`code` 折行）在 `site.css`。

## 8. 配置

`radar/contribution_repos.json`：数组，元素是 `"owner/repo"` 或 `{"repo": "...", "focus": true, "young": true}`。

- `focus`：候选池扩大（100 条 Issue + 定向搜索 + 120 条时间线）、卡上限 12、不满 8 张补卡、周四单独刷、首页选卡加权。
- `young`：允许提案卡；open Issue 少于 5 个的仓库自动视为 young。

## 9. 本地验证与排查

```bash
python3 -m pytest -q tests                      # 现有单测（目前只覆盖 jobs）
python3 tools/contributions.py --list [--focus] # CI 矩阵用的仓库列表
python3 tools/contributions.py --merge <dir> [--scope focus] && python3 tools/build.py   # 用已有单仓库 JSON 重新合并渲染
GEMINI_API_KEY=... GITHUB_TOKEN=... python3 tools/contributions.py --only owner/repo --out out/x.json   # 跑一个仓库
```

- 渲染改动不必重跑 Gemini：手动触发工作流填 `reuse_run_id`。
- 手机端溢出检查：Playwright 打开页面，`document.documentElement.scrollWidth` 不得大于视口宽（340 / 360 / 390 / 430 都测）；对每个元素查 `scrollWidth > clientWidth` 能定位到具体溢出元素。
- 状态页 `/status/` 的源健康表里「开源贡献」一栏：某仓库沿用旧结果会标出来。
- Actions 日志里搜 `丢弃` 看校验丢了哪些卡，搜 `降级` 看模型是否回退。

## 10. 已知问题

1. 架构图 / 流程图目前只有 sglang-omni 与 edge-dit.cpp 有（周四重点轮先生成），其余 12 个库要等周一全量轮。
2. 关联 PR 只看 Issue 时间线的 cross-reference；模型从 open PR 列表里发现的关联（如 omni #2183 ↔ PR #2204）不会标成 review_only，只体现在 engagement 文字里。
3. flash-attention 这类纯 CUDA 仓库只能出 Colab T4 卡，补卡后仍只有 2 张，属正常。
4. 任务卡提示词约 8 万 token，一次约 2–3 分钟；每周全量约 14 × 7 次调用。
5. `evidence.issues[].prs_checked=false` 的 Issue 不进候选池，超出时间线查询上限的长尾 Issue 会被忽略。
6. 章节文字质量依赖 README 与源码片段是否被采到；纯 C++ 仓库的 `key_files` 只认几种固定文件名。

## 11. 待办 / 功能想法（按价值排序）

1. **进度状态**：给任务卡加「已认领 / 已提 PR / 已合并」的本地标记（localStorage 或一个人工维护的 JSON），下次生成时把做过的卡排除、把认领的 Issue 跟踪 PR 状态。
2. **变化提醒**：与上一周比较，新出现 / 消失的任务卡、维护者回复了认领留言的 Issue，在首页顶部列出来；可进 RSS。
3. **认领后追踪**：对已认领 Issue 每天查 PR 状态与维护者评论，写进状态页或每日雷达。
4. **Colab 一键**：Colab T4 卡附一个最小 notebook 模板（clone + 编译 + 跑测试）。
5. **架构图增强**：点击模块跳到模块表对应行；边按类型（调用 / 数据 / 配置）区分颜色；流程图与模块表的路径互链。
6. **候选仓库发现**：按画像自动从 GitHub 搜近半年活跃、Star 增长快、有 Apple / CPU 后端的仓库，提议加入配置。
7. **章节缓存**：README / 目录树未变化时跳过第一、二章重生成，只刷第四、五章与任务卡，省一半调用。
8. **英文版页面**：认领留言已是英文；如果要给维护者看，可加英文摘要。
9. **多画像**：`PROFILE` 抽到配置文件，支持第二套画像（比如面向端侧部署方向）。
10. **单测**：给 `valid_tasks`、`candidate_pool`、`arch_svg` 补固定样例的单测，防止回归。

## 12. 常见改动去哪改

| 想做什么 | 改哪里 |
|---|---|
| 加 / 减仓库、设重点、允许提案卡 | `radar/contribution_repos.json` |
| 改候选人画像、算力约束 | `PROFILE` 常量；任务卡规则 3 / 11 |
| 改某一章要写什么 | `CHAPTERS`（schema）+ `CHAPTER_BRIEF`（要求）+ `analysis_html`（渲染） |
| 改任务卡字段 | `TASK` schema + 提示词硬约束 + `task_card` |
| 改校验规则 | `valid_tasks`、`ENV_ONLY` / `GPU_ONLY` / `REVIEW_CAP` |
| 改首页选卡逻辑 | `render()` 的 `picks` |
| 改图的样式或布局 | `arch_svg` / `flow_svg` + `detail_page` 里的 `.d-*` 样式 |
| 改频率或范围 | `contributions.yml` 的 cron 与 `plan` 步骤 |
| 改模型、超时、重试 | `contributions.yml` 的 env；`tools/radar.py` 的 `call_gemini_json` |
