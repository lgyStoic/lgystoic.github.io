# PRD：工作机会（/radar/jobs/）

> 代码：`tools/jobs.py`（官方渠道抓取与匹配）、`tools/import_liepin.py`、`tools/import_ats_jobs.py`、`tools/jobbuddy_enrich.py`、`tools/jobs_ai.py`；配置：`radar/job_sources.json`、`radar/ats_companies.json`；数据：`radar/data/jobs.json`；工作流 `.github/workflows/jobs.yml`（每天 00:35 UTC）；单测 `tests/test_jobs.py`。

## 1. 目标与非目标

**目标**：每天把与站长方向（GPU Kernel、AI Infra、DiT、端侧部署、训推加速）匹配的岗位聚合到一页，**深圳优先，其次香港与国内其他城市，再远程与海外**；每条给出可解释的匹配理由与匹配度。

**非目标**：不做投递、简历、薪资谈判；不匹配经验 / 学历 / 签证（页面明示）；不收录校招、测试、售前等岗位。

## 2. 约束

- 只用官方招聘页、公开 API 和两个开源 CLI（ats-jobs、ai-job-search-cn 的猎聘 skill）；不登录、不绕验证码。
- 每家公司国内最多 3 条、海外最多 3 条，避免一家刷屏；猎头岗位按地区与标题去重，总量最多 30 条、每地区最多 8 条。
- 源失败沿用上次该源的岗位并标 stale；外部适配器（猎聘、ats-jobs）失败时保留上次结果。
- 单次 job 30 分钟；猎聘 CLI 单次 90 秒、连续 4 个查询失败就放弃。

## 3. 功能清单

| 功能 | 说明 |
|---|---|
| 岗位页 | 搜索框（岗位 / 公司 / 地点）；chips：全部 / 深圳 / 香港 / 国内其他 / 远程 / 海外 / 高匹配 / GPU Kernel / AI Infra / DiT / 端侧部署 / 训推加速；每条：标题链接、公司、地点、匹配度徽章（高 / 中 / 低）、方向标签、匹配理由、来源、更新时间、stale 标记 |
| 手动搜索链接 | 页面末尾：LinkedIn 深圳香港 / 远程、BOSS、猎聘、拉勾、Indeed、字节社招官网、MiniMax / 月之暗面的猎聘搜索 |
| 状态页 | 「岗位」栏：每个源通 / 失败 / 已停用（附原因）/ 解析 0 条，抓取数与匹配数 |
| 状态行 | 「最近尝试更新时间」与匹配口径说明 |
| 分层展示 | 深圳 24、香港 16、国内其他 18、远程 12、海外 12 条默认展开；其余直招进入「更多匹配岗位」，匿名猎头单独折叠 |

## 4. 数据管线（`jobs.yml`）

1. `jobs.py`：19 个官方源并发抓取（3 线程），`match` 打分，`limit_jobs` 限流 → 写 `jobs.json`。停用的源不抓、不沿用旧数据，但在状态里保留一行。
2. `ats-jobs`（Node）：12 家海外公司的 12 类 ATS → `import_ats_jobs.py` 匹配合并。
3. `jobsearch-buddy`：对选中的 ATS 岗位做 URL 校验 / 补全 → `jobbuddy_enrich.py`。
4. 猎聘 CLI：5 城市 × 7 查询词，每个最多 3 次重试 → `import_liepin.py`（源 id `liepin`）。
5. `jobs_ai.py`：Gemini 对国内直招行做语义去重，每 60 条一批。
6. `build.py` 渲染，机器人提交（推送被拒时保留 `jobs.json` 重渲染）。

源类型（`kind`）：apple、workday、greenhouse、ashby、page、json、himalayas、adzuna、tencent、feishu（飞书招聘门户：CSRF 握手、站点路径探测、关键词为空时拉全量）、baidu（按 10 分页）、linkedin（guest 搜索页）。

## 5. 数据模型

`jobs.json`：`{updated, sources:[{name,ok,fetched,matched,disabled?,error}], jobs:[{title,url,company,location,region,level,tags[],reasons[],score,source,source_updated,last_seen,stale}], search_links:[{name,scope,url}]}`。

`job_sources.json`：`{profile:{title_terms[],directions{方向: 词表},title_focus[],exclude_title[],excluded_companies[],max_per_company,max_per_company_cn}, search_links[], sources:[{id,name,kind,url,queries?,locations?,path?,location?,disabled?,disabled_reason?,...}]}`。

## 6. 匹配规则（`match`）

1. 标题命中 `exclude_title`（测试 / SDET / 实习 / 校招 / 售前…）→ 丢；公司在 `excluded_companies` → 丢；标题不含任何 `title_terms` 且描述无技术词 → 丢。
2. 每个方向的词表：标题命中 +3，描述命中 +1；一个方向命中一次算一个 tag。中文词做子串匹配（`\w` 边界对汉字无效）。
3. 没有任何方向命中 → 丢。
4. `level`：score ≥6 高、≥3 中、否则低；再加地区加分（深圳 4、香港 3、国内 3、远程 2、海外 0）。
5. `region_of`：深圳 → 香港 → 国内城市词表 → 远程 → 海外。
6. 排序：地区顺序 → 质量分（技术匹配、直招、高匹配、非 stale）→ 公司 → 标题；每公司国内 / 海外最多 3 条。
7. 猎头岗位同地区、同标题只保留一条，每地区最多 8 条、全站最多 30 条；直招主列表按地区限制默认展开数量，剩余岗位进入折叠区。

## 7. 验证与排查

```bash
python3 -m pytest -q tests          # 5 个匹配 / 保留规则的单测
python3 tools/jobs.py               # 需要网络；沙箱访问不到国内招聘站
```

- Actions 日志：`源失败 <名>: <错误>`、`岗位：N；来源成功：a/b`、`猎聘：原始 N，匹配 M`、`jobs-ai：去重删除 N 条`、飞书探测记录 `{'路径': 'HTTP 400 …'}`。
- 状态页「岗位」栏看每个源；`disabled_reason` 写着为什么停。

## 8. 已知问题

1. 字节跳动（experienced 站点接口回 site not exist，只有校招能取）、MiniMax（HTTP 400）、月之暗面（0 条）三个飞书门户源已停用，靠猎聘 / LinkedIn 与手动链接覆盖；要恢复需要浏览器里抓一次真实请求头。
2. ats-jobs 里 replicate、mistral、groq、modular、stability 的 BambooHR 看板已不存在，每天打日志但无害。
3. 猎聘偶发整站不可达（fetch failed），此时沿用上次结果。
4. LinkedIn guest 页结构变了会 0 条。
5. `jobs.json` 没有记录 AI 去重用的模型。

## 9. 待办

1. 「已看过 / 不感兴趣」本地标记（localStorage），下次隐藏。
2. 新岗位提醒：与上次比较的新增列表放页面顶部，进 RSS。
3. 薪资 / 经验字段抽取（猎聘有结构化字段，可直接带过来）。
4. 修复三个飞书门户（需要真实请求样本）。
5. 香港源：加 JobsDB、LinkedIn HK 公司页。

## 10. 常见改动去哪改

| 想做什么 | 改哪里 |
|---|---|
| 加方向词、改排除词、改每公司上限 | `job_sources.json.profile` |
| 加 / 停源 | `job_sources.json.sources`（`disabled` + `disabled_reason`） |
| 改地区口径 | `region_of`、`CN_CITY_TERMS`、`REGION_ORDER / BONUS` |
| 改猎聘城市与查询词 | `jobs.yml` 的循环 |
| 改 ATS 公司名单 | `radar/ats_companies.json` |
| 改页面筛选 chips | `jobs.py render()` 与 `radar/jobs/index.html` |
