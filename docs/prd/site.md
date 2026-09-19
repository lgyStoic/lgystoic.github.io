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
| `radar.yml` AI 信息雷达 | 23:50、00:20、02:05 三个槽 + `guard` 任务（当天跑过就跳过）| 雷达 → 活动 → 收件箱 → 自检 → 提交 |
| `health.yml` 定时兜底 | 00:35、02:20 | 当天没有任何运行则 `gh workflow run radar.yml` |
| `jobs.yml` 工作机会 | 00:35 | 岗位抓取、外部适配器、AI 去重、渲染、提交 |
| `contributions.yml` 开源贡献 | 周一 01:20 全量、周四 01:20 重点 | 见 contributions.md |
| `xhs.yml` 小红书文稿 | 01:10 | 由当天雷达生成学习卡片，写入私有仓库 |

共同约定：

- cron 不放在整点（GitHub 整点丢任务），关键流水线有兜底槽。
- **推送策略**：机器人提交前 `git add -A`；被拒时不 rebase 生成物，而是保留本次数据文件、`reset --hard origin/master`、重新 `build.py`、再提交，最多三次。
- `concurrency` 按工作流分组，不取消进行中的运行。
- 每个 job 有 `timeout-minutes`；外部 CLI 调用有 `timeout` 和连续失败即止损。
- Secrets：`GEMINI_API_KEY`（必需）、`ANTHROPIC_API_KEY`（可选，有则优先）、`INBOX_TOKEN`（私有仓库 PAT）、`ADZUNA_APP_ID/KEY`、`BOOLEAN_TAVILY_API_KEY`（可选）。`GITHUB_TOKEN` 用默认的，`permissions: contents: write`。

## 5. AI 调用层（`tools/radar.py`，所有模块共用）

- `call_llm_json(system, user, schema, label)`：结构化 JSON 输出；有 Anthropic key 走 Claude，否则 Gemini；都没有返回 None，调用方退回规则。
- Gemini：`GEMINI_MODEL`（默认 `gemini-pro-latest`，实际解析为 3.1 Pro）→ 瞬时错误（超时 / 429 / 5xx）先重试首选（`GEMINI_PRIMARY_RETRIES`）→ 再降级到 `GEMINI_FALLBACK_MODEL`；`GEMINI_TIMEOUT` 默认 300 秒；`GEMINI_MAX_OUTPUT_TOKENS` 默认 16384。
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
