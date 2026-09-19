# PRD：活动清单（/radar/events/）

> 代码：`tools/events.py`、`tools/build.py`（`render_events_page` 等）；配置：`radar/event_sources.json`；数据：`radar/data/events.json`；随 `radar.yml` 每天运行。

## 1. 目标与非目标

**目标**：把深圳、广州、香港及线上可以报名参加的 AI 聚会、黑客松、比赛、讲座、大会、学术截止按日期排好，抽出日期 / 地点 / 费用 / 截止 / 主办方，标出与站长方向高度相关的。

**非目标**：不做报名、日历同步、提醒推送；不收录非 AI / 系统方向的泛活动；不抓需要登录的平台。

## 2. 约束

- 源类型受限于公开数据：`rss / json`（复用雷达解析）、`ics`（lu.ma、Google 日历）、`page`（列表页抽链接再抓详情页的 OG / JSON-LD Event）、`yaml`（ai-deadlines）、`wechat`（公众号列表）。
- 每轮上限：每源候选 40、详情页抓取 120、新增 260；过去 14 天内的活动保留在「已过去」。
- 模型只做「是不是活动 + 抽字段 + 相关度」，字段缺失用源默认值（默认类型、默认城市）。

## 3. 功能清单

| 功能 | 说明 |
|---|---|
| 活动页 | 统计行；筛选 chips（城市 → 线上 → 类型 → 推荐，只列实际出现过的）；即将发生列表按锚定日期排序；相关度 high 加 ★；low 相关度不进主列表；已过去折叠 |
| 活动行 | 日期（今天 / 明天 / 周几）、标题链接、类型、城市 / 线上、费用、截止、主办方、一句话摘要、AI 标记 |
| 首页 | 「近期活动」区块 |
| 雷达每期页 | 一行指引到活动页（不内嵌列表） |
| 状态页 | 源健康表「活动」栏 |

## 4. 数据管线

1. `collect`：按源解析候选（五种解析器）；`seen` 去重（id + 标题）；`exclude_pattern / link_pattern` 过滤。
2. `fetch_detail`：对候选抓详情页，读 OG、JSON-LD Event、正文片段。
3. `enrich_events`：模型判断是否活动，抽 `event_type / start / end / deadline / city / online / fee / organizer / summary / relevance`。
4. `to_event`：合并默认值、校验日期；与旧数据合并，过期 14 天以上的删除。
5. 写 `events.json`，`build.py` 渲染。

## 5. 数据模型

`events.json`：`{updated, today, model, sources:[...], events:[{id,title,link,source,source_id,found,event_type,start,end,deadline,city,online,fee,organizer,summary,relevance(high|medium|low),ai}], seen:{id: 首见日期}}`。

`event_sources.json`：`{site:{cities,keep_past_days,max_candidates_per_source,max_new_per_run,max_detail_fetch}, types{7 种}, sources:[{id,name,kind,url,link_pattern?,exclude_pattern?,base?,default_type,default_city,...}]}`。

## 6. 规则

- 排序锚点：有 `start` 用 start，否则 `deadline`；都没有排最后。
- 「即将」= 结束日期或锚点 ≥ 今天；相关度 low 不在主列表但保留在数据里。
- 巡检自动停用规则与雷达相同。

## 7. 验证与排查

```bash
python3 tools/events.py --dry-run
```

- 日志：每源候选数、详情抓取数、模型抽取结果；`[events-ai]` 段。
- 抽取明显错（日期、城市）属「需人判断」，巡检会写进 `health.json.needs_agent`。

## 8. 已知问题

1. lu.ma 等页面源依赖 HTML 结构，改版即失效，只能靠巡检发现。
2. 微信公众号列表源不稳定。
3. 同一活动多个源重复时靠标题近似去重，海报图文类活动去重效果一般。
4. 没有「我要去」的标记与日历导出。

## 9. 待办

1. ICS 导出：把「即将」列表生成一个可订阅的日历文件。
2. 每周一在雷达里给「本周活动」一段摘要。
3. 香港 / 广州源偏少，补 Meetup、Eventbrite 城市页。
4. 相关度阈值与站长反馈联动（点「不相关」后进 mute 列表）。

## 10. 常见改动去哪改

| 想做什么 | 改哪里 |
|---|---|
| 加 / 停源 | `radar/event_sources.json` |
| 改城市、保留天数、抓取上限 | `event_sources.json.site` |
| 改抽取字段或提示词 | `enrich_events`、`to_event` |
| 改页面筛选与排序 | `render_events_page`、`render_event_row`、`ev_anchor_date` |
