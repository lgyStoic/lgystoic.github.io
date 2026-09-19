# PRD：每日雷达（/radar/）

> 代码：`tools/radar.py`（抓取、去重、打分、AI 摘要）、`tools/build.py`（雷达首页、每期页、RSS）；配置：`radar/sources.json`；数据：`radar/data/<日期>.json`、`radar/data/seen.json`；工作流：`.github/workflows/radar.yml`。

## 1. 目标与非目标

**目标**：每天早上 8 点前后，把二十多个模型发布、研究、性能工程、行业动态的源抓一遍，去重、按站长方向打分、由模型排优先级并写一句话中文摘要和「为什么值得看」，按必看 / 值得看 / 其余排列，附 RSS。

**非目标**：不做全文抓取和转载；不做个性化推荐以外的社交功能；不抓需要登录或硬抓的平台（小红书、微信、X 走收件箱）。

## 2. 约束

- 只用官方 RSS / 公开 JSON API / 静态页面；只依赖标准库（anthropic SDK 按需）。
- 没有 key 时退回关键词规则，摘要取描述前 160 字，页面标「关键词规则」。
- 任一源失败不影响整轮；状态写进当天数据的 `sources`。
- 定时可靠：三个 cron 槽 + `guard` + `health.yml` 兜底，当天已有任何一次运行就不重复。

## 3. 功能清单

| 功能 | 说明 |
|---|---|
| 雷达首页 | 最新一期正文 + 往期列表（日期、条数、必看预览） |
| 每期页 `/radar/<日期>/` | 统计行（条数、源通率、模式 / 模型）、失败源折叠、三组条目（必看 ≤10、值得看 ≤20、其余默认折叠）、活动清单一行指引（不再内嵌活动列表）、RSS 链接 |
| 条目 | 标题链接、来源、时间、分类标签（模型发布 / 研究论文 / 性能与基础设施 / 行业人物 / 产品与行业）、AI 摘要、为什么值得看、主题 tags |
| 首页卡片 | 状态行「日期 · 条数 · 必看 N · 模型」 |
| RSS | `radar/feed.xml`，每期一条 |
| 下游 | `xhs.py` 取当天 high / medium 前 20 条生成学习卡片；状态页与巡检读 `sources` |

## 4. 数据管线

1. `collect`：按源抓取（`kind: rss|json`；`urls` 给多个镜像按序尝试，`link_host` 把镜像域名换回原站，URL 支持 `{today}` / `{today-Nd}` 日期占位，无标题条目取正文前 120 字），JSON 源按 `json` 字段路径映射（`title` / `link` 支持 `{字段}` 模板）；解析日期、按 `window_hours`（默认 36，源可覆盖）过滤；`title_pattern` / `require_topic` 过滤；`match_tracks` 打专题标签（源 `track` 直接归属，`track_required` 不命中即丢，命中 +1 分），细节见 tracks.md；`seen.json` 去重（链接 + 标题指纹）。
2. `score_item`：`high_keywords`（标题）、`topic_keywords`（标题 + 描述）、`mute_keywords`；源 `weight` 加权 → `priority_from_score`。
3. `dedupe_titles`：跨源近似标题合并。
4. `enrich_with_ai`：模型对全部条目输出 priority / summary / why / tags（结构化 JSON）；失败退回规则。
5. `finalize` / `sort_rows` → 写 `radar/data/<日期>.json`，更新 `seen.json`。
6. `build.py` 渲染；`check.py` 自检；机器人提交。

工作流步骤：记录运行元数据 `last-run.json` → 雷达 → 活动 → 收件箱（有 `INBOX_TOKEN` 时）→ 自检 → 构建 → 提交（推送被拒时保留数据重渲染，三次）。

## 5. 数据模型

`radar/data/<日期>.json`：`{date, generated_at, ai(bool), model, sources:[{id,name,ok,count,total,error}], counts:{high,medium,low}, items:[{id,title,link,source,source_id,published,category,priority,summary,why,tags[],tracks[]}]}`。

`radar/sources.json`：`{site:{title,description,timezone,window_hours,max_high,max_medium}, categories{}, rules{high_keywords,topic_keywords,mute_keywords}, sources:[{id,name,url,urls?,link_host?,kind?,json?,category,weight,window_hours?,title_pattern?,require_topic?,track?,track_required?,disabled?,disabled_reason?,note?}]}`。分类含 `trend`（趋势榜单：HF Trending、GitHub Trending）。

## 6. 规则

- 优先级上限：必看 10、值得看 20，超出的降级。
- 源被巡检自动停用：连续失败 ≥3 天，或连续 0 条达到阈值（写 `disabled_reason`）；恢复要人工删掉 `disabled`。
- JSON 源的 `query` 参数：Algolia 类 API 要求所有词同时命中，不要写 `A OR B`；用 `require_topic` 在本地过滤。
- X（Twitter）从 Actions 抓不到（2026-09-19 探针：Nitter 镜像 451 / 403 / DNS 失败，RSSHub 404 / 503，syndication 接口 429），不要再加 X 源。人物动态改用 Bluesky 官方 RSS `https://bsky.app/profile/<handle>/rss`（条目无标题，`collect` 自动取正文前 120 字），已接 Karpathy、Lucas Beyer、hardmaru、swyx、PyTorch、Clem、Nathan Lambert、Raschka、Jeff Dean；Tri Dao / Jim Fan / Jeremy Howard / HF 官方号在 Bluesky 没发过内容，暂不接。X 的 Trends 没有可用接口，趋势用两条代替：HF Trending 里 14 天内新建且 likes ≥ 100 的模型（`published: createdAt`，`window_hours: 336`）、GitHub 30 天内新建且 500+ star 的仓库（Search API，URL 里 `{today-30d}` 由 `expand_url` 换成日期）。**趋势源必须带创建日期**：2026-09-19 用过无日期的 GitHub Trending RSS，把 DeepEP、llm.c 这类一年前的老仓库当成当日新闻，且 AI 摘要会编造「发布」事件，已弃用。
- **加源前先跑探针**：Actions → 「源探针」（`probe.yml`）填 URL，或本地 `python3 tools/probe.py <url>`；官方博客常没有 RSS（vLLM、LMSYS、Anthropic 都没有），不要凭记忆写地址。

## 7. 验证与排查

```bash
python3 tools/radar.py --dry-run
RADAR_FIXTURE_DIR=tests/fixtures python3 tools/radar.py --dry-run   # 离线用 fixture
RADAR_WINDOW_HOURS=168 python3 tools/radar.py                         # 补漏
```

- 日志：`[radar] ✓ 源名: N 条新内容（共 M 条）` / `✗ 源名: 错误`；AI 段 `[radar-ai] Gemini 完成（模型）`、`降级到 …`。
- 状态页源健康表「简报」栏；`radar/data/health.json` 连续失败 / 0 条天数。
- 沙箱里 `hn.algolia.com` 等多数外网不通，源问题要看 Actions 日志。

## 8. 已知问题

1. 每天约 17 个源抓通但当天 0 条（低频源），属正常，但会在健康表里显示黄色。
2. Hacker News 源刚重新启用（改为不带 query、100+ 分 + 主题词过滑），需观察几天。
3. 摘要质量依赖源提供的描述，纯标题的源摘要会偏短。
4. `seen.json` 只增不减，长期会变大。

## 9. 待办

1. 「本周回顾」：每周日汇总本周必看，独立页 + RSS。
2. 按分类的 RSS（只订研究、只订发布）。
3. 与开源贡献联动：雷达里出现重点仓库（sglang-omni、edge-dit.cpp）的发布或论文时高亮。
4. `seen.json` 按 90 天滚动清理。
5. 给 `radar.py` 补基于 fixture 的单测（解析、打分、去重）。

## 10. 常见改动去哪改

| 想做什么 | 改哪里 |
|---|---|
| 加 / 停源 | `radar/sources.json`（`disabled: true` 即跳过） |
| 改打分关键词、上限、时间窗 | `sources.json.rules / site` |
| 改摘要提示词或输出字段 | `enrich_with_ai`（schema 与提示）；渲染在 `render_radar_item` |
| 改每期页布局 | `render_radar_day_body`、`write_radar_days`、`RADAR_DAY_TEMPLATE` |
| 改定时 | `radar.yml` 三个 cron + `health.yml` |
