# PRD：专题追踪（视频生成模型 · 世界模型）

> 代码：`tools/tracks.py`（累积 / 抽主体 / 周综述）、`tools/radar.py:match_tracks`（打标）、`tools/build.py:write_track_pages`（页面）；配置：`radar/tracks.json`；数据：`radar/data/tracks/<id>.json`（公开）；页面：`/radar/tracks/`、`/radar/tracks/<id>/`；工作流：`radar.yml` 雷达之后一步；小红书专题日报：`xhs.yml` 每天跟学习卡片一起跑（`--tracks`），模型先判值不值得发，有料才出。

## 1. 目标与非目标

**目标**：把每日雷达里属于某个专题的条目累积成一条一直往下长的时间线，按主体（模型 / 产品）串成线程，每周由模型写一段「这周变了什么」并维护一张现状表。读者（含 AI 搜索）打开一页就能知道这个方向现在什么样、最近发生了什么。

**非目标**：不做全量论文库；不替代每日雷达；不自动发布。

## 2. 约束

- 专题条目必须来自带日期的源：无日期的榜单会把老仓库当新进展（2026-09-19 教训）。
- 综述与现状表只能用输入里的事实；模型不可用时保留上一版，时间线照常累积。
- 数据文件公开，不放密钥、不放私密内容。
- 页面手机 340–430px 不横向溢出（现状表包在 `.table-wrap` 里横向滚动；导航 7 项在窄屏换行）。

## 3. 功能清单

| 功能 | 说明 |
|---|---|
| 配置 | `radar/tracks.json`：`{id, name, blurb, keywords[], post}`。关键词大小写不敏感；英文按独立词匹配（`oasis` 不会命中 `oasisdb`），中文按子串 |
| 打标 | `radar.py:match_tracks`：源带 `track` 字段 → 直接归该专题；否则标题 + 摘要命中关键词。命中的条目 `tracks: [id]`，规则分 +1；源带 `track_required` 时不命中即丢（查询源如 Google News「Sora」会撞地名） |
| 专属源 | `sources.json` 里：HF 文生视频 / 图生视频热榜（`track: video`，14 天内新建、likes ≥ 10）、Google News 视频 / 世界模型中英查询、GitHub 30 天新仓库、arXiv cs.CV / cs.RO 日报（后四类都 `track_required`）。加源前先跑 `probe.yml` |
| 累积 | `tracks.py:build_track`：扫所有 `radar/data/<日期>.json`，把带该专题标签的条目并进 `entries`（按 id 去重，保留 180 天）；上线前的旧数据用标题 + 摘要补打标签 |
| 主体抽取 | 新条目批量交给模型：`entity`（规范短名，如 Wan2.6 / Genie 3）、`kind`（release / paper / benchmark / tool / news / opinion）；无 key 时 `fallback_entity` 取标题首个专名 |
| 线程 | `threads: {entity: [ids]}`，按条数排序；页面只展示 ≥ 2 条的线程 |
| 周综述 | 距上次 ≥ 6 天且近 7 天 ≥ 3 条 → 模型写 `digest.text`（150–300 字）、`highlights`（3–5 条）并在上一版基础上更新 `sota`（≤ 12 行：model / org / date / open_weights / spec / link / note）。`radar.yml` 手动触发 reason 填 `tracks-digest` 可强制重写 |
| 页面 | 总览 `/radar/tracks/`（卡片 + 本周要点）；专题页：简介与统计 → 本周综述 → 现状表 → 线程 → 最近 30 天时间线（按天分组）→ 更早（折叠）。`CollectionPage` + `ItemList` JSON-LD |
| 站点接入 | `site.json.modules` 加 `tracks`（导航「专题」，首页卡片显示专题数与条目数）；sitemap 与 `llms.txt` 列出专题页与本周综述摘要；`radar/data/tracks/<id>.json` 列入公开数据 |
| 小红书日报 | `xhs.py --tracks`（每天）：每个 `post` 的专题取「上一期之后、最多回看 3 天」的新条目，≥ 2 条才问模型；模型输出 `worth` / `worth_reason`，只有真正进展（发布、有结论的论文 / 评测、框架支持）才 true；true 才写稿（标题 / 正文 2–6 件进展 / 标签首个固定「视频模型日报」「世界模型日报」/ 封面 kind=track）→ 私有仓库 `posts/tracks/<id>/<日期>.md`；false 只打日志。每日卡片排序里专题条目热度 +0.1 |

## 4. 数据管线

```
sources.json（含 track / track_required 源）─▶ radar.py collect ─ match_tracks ─▶ radar/data/<日期>.json items[].tracks
                                                                                        │
                       tracks.py ◀─────────────────────────────────────────────────────┘
                         ├─ entries 累积（180 天）→ extract_entities（模型 / 兜底）→ threads
                         ├─ need_digest？→ write_digest（digest + highlights + sota）
                         └─▶ radar/data/tracks/<id>.json
                                   │                      │
                     build.py write_track_pages      xhs.py --tracks（每天，worth 才发）
                                   ▼                      ▼
                     /radar/tracks/<id>/        私有仓库 posts/tracks/<id>/<日期>.md
```

## 5. 数据模型

`radar/data/tracks/<id>.json`：`{id, name, blurb, updated, entries:[{id, date, title, link, source, priority, summary, why, tags[], entity, kind}], threads:{entity:[id]}, digest:{text, highlights[], week, generated_at, model}, sota:[{model, org, date, open_weights, spec, link, note}]}`。

雷达条目新增字段 `tracks: [id]`（空数组表示不属于任何专题；旧数据没有该字段）。

## 6. 规则

- 一条可以属于多个专题（世界模型的视频生成论文两边都进）。
- 关键词宁缺毋滥：泛词（sora、cosmos、genie、oasis、dreamer、pika）必须带版本或机构限定词，否则地名、水泥、乐队全进来。
- 综述模型优先 `gemini-flash-latest`（同全站），失败保留上一版并打日志。
- 时间线只保留 180 天；线程按条数排序，页面展示前 12 个。

## 7. 验证与排查

- 日志：`[tracks] <专题>：N 条（新增 M），K 个线程`、`[tracks] <专题>：综述已更新，现状表 R 行`、`综述未生成（模型不可用）`。
- 本地：`python3 tools/tracks.py && python3 tools/build.py && python3 tools/check_mobile.py radar/tracks/index.html radar/tracks/video/index.html`。
- 某专题条目一直为 0：先看 `radar/data/<日期>.json` 里有没有 `tracks` 非空的条目（关键词问题）→ 再看专属源是否失败（状态页源表）。
- 主体串不成线程：`entity` 不一致（模型改写了大小写 / 版本号），在 `ENTITY_SYSTEM` 里补规范化示例。

## 8. 已知问题

1. 主体抽取无 key 时用标题首个专名兜底，会出现「Recreating a 70」这类无意义主体；有 key 时不影响。
2. 综述是周更，专题页中间几天「本周综述」会显示上周的周期。
3. arXiv 日报周末为空（arXiv 周末不发布），状态页会显示 0 条，属正常。
4. 现状表完全由模型维护，日期和规格可能出错，页面已标「模型维护」。

## 9. 待办

1. 跨天去重：用 `entity` + `novelty`（same / update / new）判断学习卡片是否重复选题（见 xhs.md 待办）。
2. 专题页加「按主体筛选」的 chip 过滤（复用活动页的 tag-chip 逻辑）。
3. 更多专题（端侧推理、GPU kernel 编译器）：加一项配置即可。
4. 周综述引用条目链接（脚注），方便核对。

## 10. 常见改动去哪改

| 想做什么 | 改哪里 |
|---|---|
| 加 / 改专题、关键词 | `radar/tracks.json` |
| 加专属源 | `radar/sources.json`（`track` 或 `track_required`），先跑 `probe.yml` |
| 改综述 / 现状表口径 | `tools/tracks.py` `DIGEST_SYSTEM` |
| 改主体规范化 | `tools/tracks.py` `ENTITY_SYSTEM` / `fallback_entity` |
| 改页面版式 | `tools/build.py` `render_track_body`、`TRACK_PAGE_TEMPLATE`；样式 `site.css` 「专题追踪」段 |
| 改日报文案 / 值得发的标准 | `tools/xhs.py` `TRACK_SYSTEM`（worth 判定段）、`TRACK_TAG` |
| 改日报回看天数 / 最少条数 | `run_track_post` 里的 `timedelta(days=3)`、`len(recent) < 2` |
