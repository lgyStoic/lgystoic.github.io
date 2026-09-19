# PRD：AI 信息学习卡片（小红书学习文稿 + 封面图）

> 代码：`tools/xhs.py`；工作流：`.github/workflows/xhs.yml`（每天 01:10 UTC，可手动指定日期）；产物只进私有仓库 `lgyStoic/radar-inbox` 的 `posts/`。公开仓库只放代码，`radar/data/xhs/`、`radar/data/xhs-*.md` 已 gitignore。收件箱见 [inbox.md](inbox.md)。

## 1. 目标与非目标

**目标**：把当天雷达里 high / medium 的条目，变成可直接修改后发布的小红书内容——每条一张 3:4 封面卡片（学习卡片）+ 一段 350–700 字草稿；封面上的配图由 Gemini 生图模型生成，生不出来就退回纯排版卡片。

**非目标**：不自动发布；不做多图轮播（先只做首图）；不在公开站展示这些文稿。

## 2. 用户与约束

- 用户是站长本人，手机上打开私有仓库 `posts/<日期>.md` 就能看到封面和草稿，复制到小红书。
- 需要 `GEMINI_API_KEY`（文稿 + 生图）与 `INBOX_TOKEN`；缺 token 只写本地，缺 key 直接退出（文稿无规则退路）。
- 生图和渲染任何一步失败都不能拖垮文稿：无图 → 卡片显示大号序号；Playwright 装不上或崩了 → 只写 md。
- 文稿保留原文链接，标明「自动生成初稿，请人工核对事实和语气后再发布」；不用标题党词汇。

## 3. 功能清单

| 功能 | 说明 |
|---|---|
| 选条目 | `radar/data/<日期>.json` 里 priority ∈ {high, medium} 的前 20 条 |
| 写文稿 | 一次 `call_llm_json` 生成全部：`headline`（12–24 字）、`takeaways`（2–4 条 ≤40 字）、`post`（350–700 字，固定六段结构）、`image_prompt`（英文，极简扁平插画，禁文字/字母/logo） |
| 配图 | 前 `XHS_IMAGES`（默认 4）条调用生图：先 `GEMINI_IMAGE_MODEL` 的 `generateContent`（`responseModalities: [IMAGE, TEXT]`，读 `inlineData`），失败再试 `GEMINI_IMAGEN_MODEL` 的 `:predict`（读 `predictions[0].bytesBase64Encoded`）；都失败返回 None |
| 封面卡片 | 1080×1440 HTML（页眉「Anaxagore · AI 信息学习卡片 · 日期 · 序号」→ 560px 配图区 → 标题 → 编号要点 ≤4 → 页脚来源域名 + `lgystoic.github.io/radar/<日期>/`），Playwright Chromium 截 JPEG（质量 86，约 100–300 KB） |
| 写入 | 本地 `radar/data/xhs/<日期>/<id>.jpg` 与 `radar/data/xhs-<日期>.md`；私有仓库 `posts/<日期>/<id>.jpg` + `posts/<日期>.md`（md 内 `![封面](./<日期>/<id>.jpg)` 相对引用） |
| 排查 | `python3 tools/xhs.py --list-image-models` 列出账号可用的 image / imagen 模型及其方法；工作流勾选 `list_models` 即可 |
| 留档 | 工作流把 `radar/data/xhs/` 上传为 artifact `xhs-cards`（7 天），不用开私有仓库也能看 |

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

`SCHEMA.posts[]`：`{id, headline, takeaways[], post, image_prompt}`，`id` 必须回到当天雷达条目（不在 `byid` 的丢弃）。`posts/<日期>.md`：标题 → 提示行 → 每条 `## headline`、`![封面]`（有图才有）、原始条目、链接、**学习要点**、**小红书草稿**、`---`。

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
| `XHS_IMAGES` | 4 | 生成封面图的条数，0 关闭生图和渲染；工作流输入 `images` |
| `GEMINI_IMAGE_MODEL` | `gemini-2.5-flash-image` | 原生生图模型；仓库变量 `vars.GEMINI_IMAGE_MODEL` 可覆盖 |
| `GEMINI_IMAGEN_MODEL` | `imagen-4.0-generate-001` | 备选 Imagen 模型；`vars.GEMINI_IMAGEN_MODEL` 可覆盖 |
| `INBOX_TOKEN` / `INBOX_REPO` | — / `lgyStoic/radar-inbox` | 写私有仓库 |
| `PW_CHROMIUM` | 自动查找 | 本地 Chromium 可执行文件 |

## 9. 验证与排查

- 日志：`[xhs] 配图：<模型>`（生图成功）、`[xhs] <模型> HTTP 404/400：…`（模型名不对或未开放，用 `--list-image-models` 看真实名字，再改仓库变量）、`[xhs] 封面图 N 张（其中 M 张带生图配图）`、`[xhs] 渲染封面失败：…`、`[xhs] 生成 N 条文稿、K 张封面，写入 <repo>`。
- 想看图：Actions 该次运行的 artifact `xhs-cards`，或私有仓库 `posts/<日期>/`。
- 生图配额：Gemini 生图按张计费/限流，默认只做 4 张；配额报错（429）会自动退回无图卡片。

## 10. 已知问题

1. 生图模型名随 Google 发布更新，默认值可能过期；靠 `--list-image-models` 与仓库变量兜底。
2. 单卡内容过长（headline 超 24 字或要点超 40 字）会被卡片底部挤压，目前靠提示词约束，未做自动缩字。
3. 私有仓库每天多几百 KB 图片，一年约 100–300 MB，暂不清理。

## 11. 待办

1. 多图：第二张起按 takeaway 拆「要点卡」，形成 3–5 张轮播。
2. 让 Gemini 用配图评估一次「是否含文字 / 是否离题」，不合格重生一次。
3. 知乎 / 即刻版本文稿。

## 12. 常见改动去哪改

| 想做什么 | 改哪里 |
|---|---|
| 改文稿风格 / 字数 | `SYSTEM` |
| 改配图风格 | `SYSTEM` 里 image_prompt 段；兜底提示词在 `main()` |
| 改卡片版式 / 颜色 | `CARD_CSS`、`card_html` |
| 多生几张图 | 工作流输入 `images` 或 `XHS_IMAGES` |
| 换生图模型 | 仓库变量 `GEMINI_IMAGE_MODEL` / `GEMINI_IMAGEN_MODEL` |
| 换私有仓库 / 路径 | `INBOX_REPO`；路径在 `main()` 末尾 `gh_put` |
