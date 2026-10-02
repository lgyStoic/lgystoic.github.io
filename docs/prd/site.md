# PRD：站点框架

> 代码：`tools/build.py`（1200 行，所有页面的生成与注入）、`site.json`（模块注册表）、`site.css` / `site.js`、`.github/workflows/*.yml`。

## 1. 目标与非目标

**目标**：一个没有服务器、没有域名的个人平台。`lgystoic.github.io` 当域名，GitHub Actions 当后台，仓库里的 JSON 当数据库，GitHub Pages 当前端。三个角色：记（笔记、指南）、看（雷达、活动、岗位、开源贡献）、做（收件箱、巡检）。

**非目标**：不用前端框架和构建工具链；不做登录、用户态、服务端渲染；不在浏览器里 fetch 数据（列表全部预渲染进 HTML，禁用 JS 也能读，搜索引擎能抓到）。

## 2. 约束

- **手机优先**：站长几乎只用手机看。所有页面 340 / 360 / 390 / 430px 下 `document.documentElement.scrollWidth` 不得超过视口。
- **外部请求**：只有 GoatCounter 统计脚本和 giscus 评论区（待启用）；字体用系统字体。
- **部署**：Pages 从 `master` 根目录直接托管，没有构建步骤；`tools/build.py` 的产物（HTML、feed、sitemap）提交进仓库。
- **发布流程**：功能改动在分支上做，走 PR squash 合并到 master；Actions 机器人直接推 master。

## 3. 功能清单

| 功能 | 说明 | 代码 |
|---|---|---|
| 模块注册表 | `site.json.modules[]`：id、role、name、path、blurb、status（状态行的类型）、script、nav_label、private、card；`nav` 决定导航顺序 | `load_site`、`render_cards`、`module_status` |
| 首页 | 自我介绍 + 模块卡片（带实时状态行）+ 最新雷达 + 近期活动 + 最新笔记 + 主题标签 | `index.html` 的 `build:cards / radar / events / latest` |
| 统一页头页脚 | 品牌 A + 导航 + 深浅色开关，由 `site.json` 生成，注入所有带 `<!-- build:header -->` 的页面；当前模块高亮 | `render_site_header`、`current_module`、`inject_site_chrome` |
| 注入机制 | `<!-- build:NAME --> … <!-- /build:NAME -->` 标记内的内容每次重建替换，幂等 | `inject` |
| 深浅色 | CSS 变量在 `:root` 定义，`prefers-color-scheme` + `data-theme` 手动覆盖，记在 localStorage；同步 giscus 主题 | `site.js theme()` |
| 访问统计 | GoatCounter（站点代号 `anaxagore`，看板仅站长可见）；额外事件：推荐位点击 `aff/*`、外链 `out/*`、分享 `share/copy|native` | `render_analytics` |
| 评论 | giscus（GitHub Discussions）；`comments.repo_id / category_id` 为空时整个评论区不渲染 | `render_comments` |
| SEO | Bing / Google 站长验证 meta、`robots.txt`（屏蔽 `/radar/data/`、`/templates/`）、`sitemap.xml`（排除模板和 noindex 的状态页）、每页 canonical、OG 1200×630 卡片 `assets/og/*.png`、指南页 HowTo + 面包屑 JSON-LD | `write_sitemap`、各页 head |
| RSS | `feed.xml` 笔记、`radar/feed.xml` 雷达（每期一条） | `write_radar_feed` 等 |
| 分享条 | 「复制链接 / 分享…」（Web Share API 可用时显示原生按钮） | `site.js share()` |
| 归档搜索 | 笔记归档页关键词搜索 + 标签 chips + 年份分组隐藏，`/` 聚焦搜索框 | `site.js archive()` |

## 4. 工作流通用规则

| 工作流 | 触发（UTC） | 内容 |
|---|---|---|
| `radar.yml` AI 信息雷达 | 23:17、00:43、02:31 三个槽 + 阶段产物 guard | 雷达主数据、活动、专题、私有 inbox 分 job；雷达主数据先提交，专题等待它，最后独立巡检。活动详情页抓取预算 240 秒、模型抽取启动预算 600 秒、单次 LongCat 请求限 60 秒；各 job 单独计时和显示结果 |
| `health.yml` 定时兜底 | 01:11、03:07 | 雷达、活动或专题缺少当天已提交产物时触发 `radar.yml`；阶段 guard 只执行缺失部分 |
| `radar-alert.yml` 雷达邮件告警 | 第二次失败完成后；每天 10:17 复核（北京时间 18:17） | 同时核对当天雷达 JSON、已提交的 `last-run.json` 与工作流结果，主数据缺失或后续阶段失败时发邮件；不触发补跑 |
| `gpu-probe.yml` GPU runner 环境检查 | 仅手动触发 | 在 Windows `dd-lgystoic` runner 上检查 NVIDIA GPU、驱动、CUDA toolkit、Python、WSL、Docker 和已安装 PyTorch 的 CUDA 矩阵计算；不 checkout 项目、不安装依赖、不注入仓库 secrets |
| `gpu-docker.yml` GPU Docker 环境准备 | 仅手动触发，默认 verify-docker | prepare-wsl 启用 WSL 前置条件，等待重启；verify-docker 验证 Linux GPU 容器；reboot 必须显式选择，延迟 60 秒重启 Windows，会中断现有模型服务 |
| `jobs.yml` 工作机会 | 00:35 | 岗位抓取、外部适配器、AI 去重、渲染、提交 |
| `contributions.yml` 开源贡献 | 周一 01:20 全量、周四 01:20 重点 | 见 contributions.md |
| `xhs.yml` 小红书文稿 | 01:10 | 由当天雷达生成学习卡片，写入私有仓库 |

共同约定：

- cron 不放在整点（GitHub 整点丢任务），关键流水线有兜底槽。
- **推送策略**：由 `tools/publish_results.py` 提交；被拒时只恢复本管线拥有且本轮变化的数据，回到最新 master 用最新代码重建，最多三次。radar 不恢复 jobs/contributions 数据；源配置只合并自动停用字段，保留远端其他配置与人工状态修改。
- `concurrency` 按工作流分组，不取消进行中的运行。
- 定时重复触发仅跳过已经提交当日产物的雷达、活动和专题阶段；任何阶段失败可在下一个槽位单独补缺，不以 `last-run.json` 代表全流程成功。私有 inbox 每轮查询增量，检查阶段按 job 结果写报告。
- 每个 job 有 `timeout-minutes`；外部 CLI 调用有 `timeout` 和连续失败即止损。
- 雷达邮件告警需在仓库 Actions secrets 配置 `RADAR_ALERT_SMTP_HOST`、`RADAR_ALERT_SMTP_USER`、`RADAR_ALERT_SMTP_PASSWORD`、`RADAR_ALERT_EMAIL_TO`；可选 `RADAR_ALERT_SMTP_PORT`（默认 465）和 `RADAR_ALERT_EMAIL_FROM`。凭据缺失时告警作业失败并列出缺少的 secret 名称，不会假称邮件已发送。
- 告警定时检查按北京时间最近已到期的 18:17 交付日核对；延迟跨午夜或次日上午执行时检查上一天，不把尚未开始采集的新一天判为失败。失败运行触发按原运行 `created_at` 的北京时间日期核对；手动检查仍检查当天，邮件配置测试不变。历史交付日的数据须存在，`last-run.json` 日期不得早于交付日，允许其已被次日采集更新；仍核对目标日期的工作流结果，缺失或后续阶段失败的告警保留。
- Secrets：`GEMINI_API_KEY`（必需）、`ANTHROPIC_API_KEY`（可选，有则优先）、`INBOX_TOKEN`（私有仓库 PAT）、`ADZUNA_APP_ID/KEY`、`BOOLEAN_TAVILY_API_KEY`（可选）。`GITHUB_TOKEN` 用默认的，`permissions: contents: write`。

## 5. AI 调用层（`tools/radar.py`，所有模块共用）

- `call_llm_json(system, user, schema, label)`：结构化 JSON 输出；有 Anthropic key 走 Claude，否则 Gemini；都没有返回 None，调用方退回规则。
- Gemini：`GEMINI_MODEL`（默认 `gemini-flash-latest`，2026-09-19 起首选 Flash 线：3.8 Flash 输出质量够用、快、不易撞输出上限）→ 瞬时错误（超时 / 429 / 5xx）先重试首选（`GEMINI_PRIMARY_RETRIES`）→ 再降级到 `GEMINI_FALLBACK_MODEL`（默认 `gemini-pro-latest`）；`GEMINI_TIMEOUT` 默认 300 秒；`GEMINI_MAX_OUTPUT_TOKENS` 默认 16384（Gemini 3.x 的思考 token 也占这个预算，长输出任务给 32768）。
- 模型名全部可用仓库变量 `vars.GEMINI_MODEL` / `vars.GEMINI_FALLBACK_MODEL` 覆盖，四个工作流都读；不改代码即可切模型。
- 账号可用模型（2026-09-19，`xhs.yml` 勾 `list_models` 可重新列）：Pro 线只有 `gemini-3.1-pro-preview`（`gemini-pro-latest` 指向它）；Flash 线 `gemini-3.8-flash`（`gemini-flash-latest` 指向它）、3.7 / 3.6 / 3.5 / 3-flash-preview；生图 `gemini-3.1-flash-image`、`gemini-3-pro-image`（= nano-banana-pro）、`gemini-2.5-flash-image`，没有 Imagen。API 里没有 3.8 Pro；站长实测 3.8 Flash 文稿质量可接受，故全站首选 Flash 线，Pro 作备选。
- `LAST_MODEL_USED` 记录实际模型版本，写进各数据文件的 `model` 字段并显示在页面上。

## 6. 验证与排查

```bash
python3 tools/build.py            # 全站重建（幂等）
python3 -m pytest -q tests        # 单测
python3 -m http.server 8765       # 本地预览
```

- 手机溢出检查：Playwright 打开每个代表页面，四个视口宽度下比较 `scrollWidth`；逐元素 `scrollWidth > clientWidth` 定位溢出源。桌面 Chrome 窄窗口截图**不可信**（窗口有最小宽度，截图是裁出来的）。
- 内部链接检查：遍历所有 HTML 的 href/src，相对路径必须能落到文件。
- `/status/` 页看最近一次运行、巡检报告、源健康表。

## 7. 已知问题

1. giscus 评论区未启用：需要仓库开启 Discussions、安装 giscus App，把 `repo_id`（已知 `MDEwOlJlcG9zaXRvcnkyMzAwMzg5Njk=`）和 `category_id` 填进 `site.json`。
2. 没有自定义域名；搜索权重与 CDN 受 github.io 限制。若买域名，优先 Cloudflare 托管 + Pages 自定义域。
3. 部署环境（Claude Code 沙箱）访问不到多数国内站点和 Azure blob，涉及这些的问题只能靠 Actions 日志排查。
4. 沙箱里的 CSS 类使用统计显示全部 132 个类都有引用；新加样式时注意别遗留死代码。

## 8. 待办

1. giscus 启用（等站长提供 category_id）。
2. 自定义域名 + Cloudflare（顺带解决国内访问速度）。
3. 给 `build.py` 拆文件：站点框架 / 雷达 / 活动 / 指南 / 状态各一个模块，现在 1200 行在一个文件里。
4. Playwright 溢出检查做成 `tests/` 里的可选测试，Actions 里跑一次（需要安装浏览器，约 1 分钟）。
5. 首页模块卡片状态行加「最近一次运行是否成功」。

## 9. 常见改动去哪改

| 想做什么 | 改哪里 |
|---|---|
| 加一个模块 | `site.json.modules` 加一行；页面里放 `build:header / site-name / analytics` 标记；如需状态行在 `module_status` 加分支；数据脚本放 `tools/`，工作流放 `.github/workflows/` |
| 改导航顺序或名字 | `site.json.nav`、各模块的 `nav_label` |
| 改配色 / 字体 / 断点 | `site.css` 顶部的 `:root` 变量与 `@media` |
| 改统计或评论 | `site.json.analytics / comments` |
| 改站长验证码 | `site.json.seo.verification`（bing / google / baidu / sogou / shenma），build 注入首页 |
| 改 OG 图 | `assets/og/`；各页 `<head>` |
| 改机器人推送策略 | 各 workflow 的「提交结果」步骤（四个工作流写法一致，改一处要同步） |


## 10. 管线提交与回归（2026-09-28）

- radar、jobs、contributions 共用 `tools/publish_results.py <owner> --message <中文说明>`；xhs 通过 GitHub API 写私有仓库，采用独立的检查点机制。
- radar 拥有当日 JSON、seen、活动、专题、health、last-run 与巡检报告；jobs 仅拥有 jobs.json；contributions 仅拥有 contributions.json。恢复只覆盖本轮变更的归属文件；保留其他管线与最新主分支的数据，随后重新构建页面。
- 源自动停用按 source id 合并 disabled/disabled_reason 字段；若远端同时改了这些字段，保留远端状态并记录日志，避免抹去人工决定。
- `check.yml` 在 PR 和手动触发时运行离线回归与构建，不需要生产凭据。`tests/test_publish_results.py` 使用临时裸仓库与两个 checkout 重现并验证交错推送。
