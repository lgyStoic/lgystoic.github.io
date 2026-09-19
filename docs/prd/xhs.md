# PRD：小红书文稿（每日学习卡片 + 周一岗位精选）

> 代码：`tools/xhs.py`；工作流：`.github/workflows/xhs.yml`（每天 01:10 UTC 学习卡片；每周一 01:40 UTC 岗位周报；手动可选 mode / date / 地区）；产物只进私有仓库 `lgyStoic/radar-inbox` 的 `posts/cards/`、`posts/jobs/`，`posts/README.md` 是自动索引。公开仓库只放代码，`radar/data/xhs/`、`radar/data/xhs-*.md` 已 gitignore。收件箱见 [inbox.md](inbox.md)。

## 1. 目标与非目标

**目标**：把当天雷达里 high / medium 的条目，变成可直接修改后发布的小红书内容，并服务账号涨粉（目标 1000 粉）：每条正文末尾有绑定系列定位的关注引导，封面页眉「每天一张」、页脚「关注看每日更新 · 收藏回头翻」，标签首个固定 `#AIInfra学习卡片` 做系列聚合——每条一张 3:4 封面卡片（学习卡片）+ 一段 350–700 字草稿；封面上的配图由 Gemini 生图模型生成，生不出来就退回纯排版卡片。

**非目标**：不自动发布；不做多图轮播（先只做首图）；不在公开站展示这些文稿。

## 2. 用户与约束

- 用户是站长本人，手机上打开私有仓库 `posts/<日期>.md` 就能看到封面和草稿，复制到小红书。
- 需要 `GEMINI_API_KEY`（文稿 + 生图）与 `INBOX_TOKEN`；缺 token 只写本地，缺 key 直接退出（文稿无规则退路）。
- 生图和渲染任何一步失败都不能拖垮文稿：无图 → 卡片显示大号序号；Playwright 装不上或崩了 → 只写 md。
- 正文里不放 URL、不放小节标签，标题 ≤20 字（小红书硬限制）；原文链接只在 md 里单独列出。标明「自动生成初稿，请人工核对事实和语气后再发布」；不用标题党词汇。

## 2.5 私有仓库目录（2026-09-19 起）

```
posts/
  README.md            自动索引：两类各最近 30 期
  cards/<日期>.md       每日学习卡片文稿（20 条）
  cards/<日期>/<id>.jpg 封面（前 N 条）
  jobs/<日期>.md        岗位周报文稿 + 核对用明细表
  jobs/<日期>/cover.jpg 封面 1 张
```
2026-09-19 之前的 `posts/<日期>.md` 与 `posts/<日期>/` 是旧格式，原样保留不迁移。

## 3. 功能清单

### 3.1 每日学习卡片（cards）

| 功能 | 说明 |
|---|---|
| 选条目 | `radar/data/<日期>.json` 里 priority ∈ {high, medium} 的前 20 条 |
| 写文稿 | 一次 `call_llm_json` 生成全部：`headline`（12–24 字，封面用）、`takeaways`（2–4 条 ≤40 字，封面用）、`title`（小红书标题 ≤20 字）、`body`（300–600 字，短段落空行分隔，禁小节标签、禁 URL、第一句要有钩子、第一人称）、`tags`（3–5 个话题词，首个固定系列词 `AIInfra学习卡片`）、`image_prompt`（英文极简扁平插画，禁文字/logo）。`clean_post` 再兜底清掉泄漏的「标题：/开头：」标签与 URL，标签去空格、截 5 个，title 截 20 字 |
| 配图 | 前 `XHS_IMAGES`（默认 4）条调用生图：按 `GEMINI_IMAGE_MODEL`（逗号分隔，默认 `gemini-3.1-flash-image,gemini-2.5-flash-image`）依次调 `generateContent`（`responseModalities: [IMAGE, TEXT]`，读 `inlineData`）；可选再试 `GEMINI_IMAGEN_MODEL` 的 `:predict`（账号无 Imagen 时留空）；都失败返回 None |
| 封面卡片 | 1080×1440 HTML（页眉「Anaxagore · AI 信息学习卡片 · 日期 · 序号」→ 560px 配图区 → 标题 → 编号要点 ≤4 → 页脚来源域名 + `lgystoic.github.io/radar/<日期>/`），Playwright Chromium 截 JPEG（质量 86，约 100–300 KB） |
| 写入 | 本地 `radar/data/xhs/<日期>/<id>.jpg` 与 `radar/data/xhs-<日期>.md`；私有仓库 `posts/<日期>/<id>.jpg` + `posts/<日期>.md`。md 每条：封面 → **标题** → **正文** → `#标签` 一行（复制即发）→ 原文名 + 链接（单独给人决定是否放评论区）→ 折叠的封面要点 |
| 排查 | `--list-models` / `--list-image-models` 列账号可用模型；工作流勾 `list_models`。勾 `preview` 把第 1 条标题正文打到日志（检查文风，日志公开可见，文稿本身不敏感） |
| 留档 | 工作流把 `radar/data/xhs/` 上传为 artifact `xhs-cards`（7 天），不用开私有仓库也能看 |

### 3.2 岗位周报（jobs，`--jobs`）

| 功能 | 说明 |
|---|---|
| 选岗位 | `pick_jobs`：`radar/data/jobs.json` 里公司名真实（排除 `某…`、`知名`、`保密`、`匿名`）、未 stale、地区符合 `XHS_JOBS_REGION`（空=全部，cn=国内/深圳/香港，overseas=海外/远程）；分数高优先、同分新发布优先；每家公司 ≤2 条；取 12 条；少于 5 条跳过 |
| 写文稿 | `JOBS_SYSTEM` + `JOBS_SCHEMA`：`headline`、`highlights`（封面 4–6 行「公司 · 地点 · 方向」）、`title`（≤20 字带数量）、`body`（350–650 字：一句整体观察 → 逐条「公司｜岗位｜地点 — 为什么值得看」→ 关注引导）、`tags`（首个固定 `AIInfra岗位`）、`image_prompt`。硬规则：不编薪资/年限/流程，不说内推/私信，不放 URL，公司名规范化 |
| 封面 | `card_html(kind='jobs')`：页眉「AI infra 岗位精选 · 每周一 · N 个岗位」，要点区 6 行紧凑，页脚指向 `/radar/jobs/` |
| md | 封面 → 标题 → 正文 → 标签 → 「岗位明细（核对用，不发）」表：公司 / 岗位 / 地点 / 分数 / 来源 / 链接，以及筛选条件 |

## 4. 数据管线

```
radar/data/<日期>.json ─筛 high/medium 前20─▶ call_llm_json(SYSTEM, SCHEMA) ─▶ posts[]
                                                                             │
                                  前 N 条 ─▶ gemini_image(image_prompt) ─┐   │
                                                                         ▼   ▼
                                                   card_html(index, post, src, date, art_b64)
                                                                         │
                                            render_cards(Playwright) ─▶ radar/data/xhs/<日期>/<id>.jpg
                                                                         │
                       md（每条：封面 / 原始条目 / 链接 / 学习要点 / 草稿）◀─┘
                                                                         │
                                                gh_put ─▶ 私有仓库 posts/<日期>/*.jpg, posts/<日期>.md
```

## 5. 数据模型

`SCHEMA.posts[]`：`{id, headline, takeaways[], title, body, tags[], image_prompt}`，`id` 必须回到当天雷达条目（不在 `byid` 的丢弃）。`posts/<日期>.md`：标题 → 提示行 → 每条 `## NN headline`、`![封面]`（有图才有）、**标题**、**正文**、`#标签`、原文、链接、`<details>` 封面要点、`---`。

## 6. 规则

- 卡片顺序 = 雷达顺序（分数高的在前），序号从 01 起；只给前 N 条生图，其余卡片不渲染（节省时间，md 仍有全部草稿）。
- 生图提示词由模型给（英文），为空时用 headline 兜底拼一句；两条模型都失败只记日志。
- 配图 `object-fit: cover` 填满 560px 区域，因此提示词要求 1:1 或近方构图、无文字。
- 中文字体依赖 `fonts-noto-cjk`（Actions 里 apt 安装），本地缺字体会出方块但不报错。

## 7. 渲染

`CARD_CSS` 内嵌在 HTML 里，颜色与站点一致（背景 #fbfaf8、强调 #9a3412、正文 #1b1b1a）。改版式只动 `CARD_CSS` / `card_html`，本地可用 `python3 -c` 拼一条假 post 调 `render_cards` 看效果（需 `pip install playwright`，Chromium 路径取 `PW_CHROMIUM` 或 `/opt/pw-browsers/chromium-*`）。

## 8. 配置

| 变量 | 默认 | 说明 |
|---|---|---|
| `RADAR_DATE` | 今天（Asia/Shanghai） | 生成哪天的；工作流输入 `date` |
| `--jobs` / 工作流 `mode` | cards | jobs 只出岗位周报，both 都出；周一 01:40 UTC 的 cron 自动走 jobs |
| `XHS_JOBS_REGION` | 空 | 岗位周报地区：cn / overseas；工作流输入 `jobs_region` |
| `XHS_IMAGES` | 4 | 生成封面图的条数，0 关闭生图和渲染；工作流输入 `images` |
| `GEMINI_IMAGE_MODEL` | `gemini-3.1-flash-image,gemini-2.5-flash-image` | 原生生图模型，逗号分隔按序尝试；仓库变量 `vars.GEMINI_IMAGE_MODEL` 可覆盖（2026-09 账号可用：gemini-3.1-flash-image / -lite-image、gemini-3-pro-image、gemini-2.5-flash-image） |
| `GEMINI_IMAGEN_MODEL` | 空 | 可选 Imagen `:predict` 兜底；账号列表里没有 Imagen 就别设 |
| `INBOX_TOKEN` / `INBOX_REPO` | — / `lgyStoic/radar-inbox` | 写私有仓库 |
| `PW_CHROMIUM` | 自动查找 | 本地 Chromium 可执行文件 |

## 9. 验证与排查

- 日志：`[xhs] 配图：<模型>`（生图成功）、`[xhs] <模型> HTTP 404/400：…`（模型名不对或未开放，用 `--list-image-models` 看真实名字，再改仓库变量）、`[xhs] 封面图 N 张（其中 M 张带生图配图）`、`[xhs] 渲染封面失败：…`、`[xhs] 生成 N 条文稿、K 张封面，写入 <repo>`。
- 想看图：Actions 该次运行的 artifact `xhs-cards`，或私有仓库 `posts/<日期>/`。
- 生图配额：Gemini 生图按张计费/限流，默认只做 4 张；配额报错（429）会自动退回无图卡片。

## 10. 已知问题

1. 生图模型名随 Google 发布更新，默认值可能过期；靠 `--list-image-models`（工作流勾 `list_models`）与仓库变量兜底。2026-09-19 列表里没有 Imagen 模型。
2. 单卡内容过长（headline 超 24 字或要点超 40 字）会被卡片底部挤压，目前靠提示词约束，未做自动缩字。
4. 2026-09-19 前的版本正文会带「标题：/开头：」小节标签、写成新闻稿口吻且含 URL，无法直接发布；已改提示词并加 `clean_post` 兜底。
3. 私有仓库每天多几百 KB 图片，一年约 100–300 MB，暂不清理。

## 11. 待办

1. 多图：第二张起按 takeaway 拆「要点卡」，形成 3–5 张轮播。
2. 让 Gemini 用配图评估一次「是否含文字 / 是否离题」，不合格重生一次。
3. 知乎 / 即刻版本文稿。
4. 岗位周报按地区轮换（国内 / 海外远程交替），或一周两期。

## 12. 常见改动去哪改

| 想做什么 | 改哪里 |
|---|---|
| 改文稿风格 / 字数 / 段落规则 | `SYSTEM`（body 的 9 条硬性要求：第 8 条防编造，第 9 条关注引导——绑定「每天一张 AI infra 学习卡片」的账号定位，措辞每条不同，禁模板话）；系列标签常量 `SERIES_TAG`；兜底清洗在 `clean_post` |
| 改配图风格 | `SYSTEM` 里 image_prompt 段；兜底提示词在 `main()` |
| 改卡片版式 / 颜色 | `CARD_CSS`、`card_html` |
| 多生几张图 | 工作流输入 `images` 或 `XHS_IMAGES` |
| 换生图模型 | 仓库变量 `GEMINI_IMAGE_MODEL` / `GEMINI_IMAGEN_MODEL` |
| 换私有仓库 / 路径 | `INBOX_REPO`；路径在 `out_paths`，写入在 `publish` |
| 改岗位筛选（条数 / 每家上限 / 匿名规则） | `pick_jobs`、`ANON_RE` |
| 改岗位文案规则 | `JOBS_SYSTEM` |
