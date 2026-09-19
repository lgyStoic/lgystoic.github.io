# PRD：GEO（让 AI 搜索引用本站）

> GEO = Generative Engine Optimization：让 ChatGPT 搜索、Perplexity、Gemini、Kimi、豆包、DeepSeek 联网搜索这类「会给出处的回答」在引用来源里出现本站。站内部分由 `tools/build.py` 自动生成；站外部分要人做。

## 1. 原理（决定策略的三件事）

1. **AI 搜索不自己爬全网，先查传统索引再读页面。** ChatGPT / Perplexity / Copilot 主要走 Bing 索引，Gemini 走 Google，国内的豆包 / 文心 / DeepSeek 联网主要走百度与自家索引，Kimi 混用。所以 GEO 的地基仍是 SEO：被 Bing、Google、百度收录，且 sitemap 与 lastmod 准确。
2. **模型偏爱能直接引用的句子。** 一段话第一句就给结论、带数字和日期、实体名字前后一致（Anaxagore / lgystoic.github.io）、有明确的「是什么 / 怎么做 / 结果如何」结构，比长篇叙述更容易被抽出来当引文。
3. **结构化数据与 llms.txt 是给机器的说明书。** schema.org 让引擎知道页面是教程 / 文章 / 活动，`llms.txt` 让大模型爬虫一次拿到全站地图和引用方式。

## 2. 站内已实现（build 自动维护）

| 项 | 内容 | 位置 |
|---|---|---|
| `/llms.txt` | 站点简介、作者与引用方式、三篇指南、全部笔记（标题 + 摘要 + 更新日期）、最近 7 期雷达的必看条目、活动 / 岗位 / 开源贡献入口与每个仓库页、公开 JSON 数据接口说明 | `write_llms_txt` |
| robots.txt | 明确允许 GPTBot、OAI-SearchBot、ChatGPT-User、ClaudeBot、PerplexityBot、Google-Extended、Applebot-Extended、Bytespider（豆包 / 头条）、DuckAssistBot、Amazonbot、CCBot、cohere、Mistral、YouBot、Meta 等；只禁 `/templates/` | `robots.txt` |
| 首页 | `WebSite` + `Person`（@graph，sameAs GitHub，jobTitle，深圳，knowsAbout） | `index.html` |
| 指南页 | `HowTo`（步骤取自 `<ol class="steps">`）+ `BreadcrumbList`，含 author / publisher / image / dateModified | `render_guide_jsonld` |
| 笔记页 | `BlogPosting`（headline、description、keywords、dateModified、isBasedOn、author） | `render_note_jsonld` + 页面 `<!-- build:jsonld -->` 标记 |
| 雷达每期页 | `Article` + 必看条目 `ItemList` | `render_radar_jsonld` |
| 活动页 | 即将发生的活动 `ItemList<Event>`（startDate、endDate、线上 / 城市、organizer），最多 50 条 | `render_events_jsonld` |
| 开源贡献仓库页 | `TechArticle` + `about: SoftwareSourceCode` | `contributions.detail_page` |
| 指南页 FAQ | 「不通时先查这四项」表格 → `FAQPage`（问题自动加「怎么办？」） | `render_guide_jsonld` |
| 站长验证 | `site.json.seo.verification`（bing / google / baidu / sogou / shenma），非空即注入首页 head；拿到百度验证码只需填一行 | `render_verification` |
| 每月提醒 | 每月 1 日的巡检报告「待人决定」里列站外清单 | `check.py` |
| 基础 SEO | canonical、OG 卡片、sitemap（含 lastmod）、RSS ×2、长尾标题 | 各页 head、`write_sitemap` |

验证：`python3 tools/build.py` 后，所有 `application/ld+json` 块可被 `json.loads` 解析（目前 42 块）；`llms.txt` 约 75 行。

## 3. 内容规则（写新页面时遵守，这是 GEO 的大头）

- **首段给结论**：每页第一段用一两句把「这页解决什么、结论是什么」说完，数字带日期（「2026 年 9 月，芝麻租赁 MacBook Air M3 16G+512G 月租 299 元」）。
- **可引用的定义句**：每个概念给一句「X 是 …」的独立句子，不夹在长句里。
- **问答式小标题**：「不通时先查这四项」「订 Plus 就够了」这类标题正是模型抽答案的锚点；能改成问句的改成问句。
- **实体一致**：作者名只用 Anaxagore（括注 lgyStoic），站名只用 lgystoic.github.io；不要再出现旧名字。
- **标日期**：每页显示更新日期（指南、笔记已有），模型偏爱新鲜内容。
- **原始数据**：给出可核对的来源链接与 JSON 数据接口，「有数据的页面」比「有观点的页面」更常被引用。
- **中文为主，关键术语保留英文原文**，方便中英文提问都命中。

## 4. 站外（人做，按优先级）

1. **Bing Webmaster**：sitemap 已提交；新页面用「URL 提交」手动推一次（ChatGPT / Perplexity / Kimi 的召回主要靠它）。
2. **Google Search Console**：同上；Gemini 与 AI Overview 走这里。
3. **百度站长**：github.io 域名收录慢但可做；把验证码填进 `site.json.seo.verification.baidu`，构建后提交 sitemap。豆包 / 文心 / DeepSeek 联网主要靠它。买了域名后优先级提高。
4. **被引用**：GitHub 仓库 README 与 About 写站点地址；在 LinuxDo、V2EX、知乎回答里作为来源链接出现（文案在 `.github/promo/`）；把「深圳地铁 200 米小区清单」这类数据型笔记投到相关社区，数据页最容易被 AI 搜索当来源。
5. **实体建立**：GitHub 个人主页简介、知乎 / LinkedIn 简介都写同一个名字和站点地址，让引擎把 Anaxagore 和站点绑定。

## 5. 度量

- GoatCounter 看板的来源站：`chatgpt.com`、`perplexity.ai`、`kimi.com`、`doubao.com`、`bing.com`、`google.com` 的占比变化是 GEO 的直接信号。
- Bing Webmaster / Search Console 的收录页数与展示次数。
- 每月手动问一次三家 AI 搜索「离职后怎么租电脑过渡」「深圳 AI 活动」「sglang-omni 怎么参与贡献」，看是否引用本站。

## 6. 待办

2. 每页生成 Markdown 副本（`index.md`）并在 `llms.txt` 链接，降低模型读取成本。
3. 岗位页 `JobPosting` 结构化数据（需要保留 description 与 datePosted 字段）。
4. 自定义域名 + Cloudflare：提升百度收录与国内访问速度。
5. 把「站外清单」第 1–3 项做成每月一次的巡检提醒。

## 7. 常见改动去哪改

| 想做什么 | 改哪里 |
|---|---|
| 改 llms.txt 的介绍或分区 | `write_llms_txt` |
| 加 / 减允许的爬虫 | `robots.txt` |
| 给新类型页面加结构化数据 | 在 `build.py` 写 `render_<x>_jsonld`，页面 head 放 `<!-- build:<x>-jsonld -->` 标记，`main()` 里 inject |
| 改作者实体信息 | `index.html` 的 `@graph`，以及 `render_*_jsonld` 里的 author |
