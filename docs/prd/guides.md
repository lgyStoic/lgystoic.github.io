# PRD：上手指南（/guides/）

> 页面：`guides/index.html`、`guides/pc/`、`guides/proxy/`、`guides/chatgpt/`；配置：`guides/guides.json`（篇目）、`guides/links.json`（推荐链接注册表）；构建：`tools/build.py` 的 `build_guides` 系列；曝光材料：`.github/promo/`。

## 1. 目标与非目标

**目标**：给离职后第一次从零上手 AI 工具的人一条三步路径——租一台电脑 → 装好代理 → 注册并订阅 ChatGPT——每一步只给一个主推方案和必要的备选；通过推荐位（CPS）获得收入；被搜索引擎收录、被转发。

**非目标**：不写「免费 / Team / 企业版」这类站长没有亲测的内容；不做地址生成器等工具页；不在页面上出现「推广」「含推广链接」之类的免责声明（用词统一为「推荐」）；敏感题材（代理、ChatGPT）不主动往外投放，只靠搜索进来。

## 2. 约束

- 站长亲测的写清楚，未亲测的标「未亲测」（如 iPhone 美区礼品卡路径）。
- 推荐链接只在注册表里维护，页面用 `data-aff="key"` 占位；链接为空的推荐位整块隐藏。
- 价格、套餐等易变信息尽量少写数字，写了要有来源。
- 手机端：两张收款码并排不能撑开页面；长命令用 `<pre>`。

## 3. 功能清单

| 功能 | 说明 | 代码 |
|---|---|---|
| 指南首页 | 三步路径卡片（步骤号、标题、一句话、更新时间），草稿也可点进去 | `render_guides_path` |
| 第一步 · 租电脑 | 四条路线对比表（短租实体机 / 云电脑 / 按小时 GPU / 二手）；主推芝麻租赁 MacBook Air M3 16G+512G 月租 299（支付宝小程序，无链接，`.offer.plain` 亲测卡）；备选云电脑、Colab 免费 T4、compshare GPU、腾讯云小服务器（只适合 24h 跑任务，不是电脑）；下一步导航 | `guides/pc/index.html` |
| 第二步 · 代理 | 选套餐购买（Shadowsocks 推荐位）、原理一分钟、电脑五步（Clash Verge Rev）、手机（Android Clash Meta、iOS Shadowrocket 需海外 Apple ID）、排查四项 | `guides/proxy/index.html` |
| 第三步 · ChatGPT | 办 Visa 卡（招行全币种 / 双币，向业务员说明卡种）、Play 商店切海外区（手机端切不了时用 `play.google.com/settings` 网页；地址按搜索「日本地址生成器」自行获取）、登录并在 Play 内购订阅 Plus、只订 Plus、排查四项；iPhone 走美区礼品卡（未亲测） | `guides/chatgpt/index.html` |
| 推荐位 | `.offer` 卡片（标签、正文、怎么用）与行内 `<a data-aff>`；build 填链接、空则隐藏；点击上报 GoatCounter `aff/<key>` | `apply_affiliate_links` |
| 支持块 | 「这篇内容帮到你了吗」微信 / 支付宝收款码，注入到每页末尾 | `apply_guide_support` |
| 结构化数据 | HowTo（从 `<ol class="steps">` 生成）+ 面包屑 JSON-LD；长尾搜索标题；OG 卡片 | `render_guide_jsonld`、`assets/og/{guides,pc,proxy,chatgpt}.png` |
| 分享条 | 复制链接 / 原生分享，事件上报 | `site.js share()` |
| 评论区 | giscus 标记已放好，等 `site.json` 填 id | `render_comments` |

## 4. 数据模型

`guides/guides.json`：`[{id, step, title, path, blurb, status: published|draft, updated}]`。

`guides/links.json`：`{ _readme, links: { <key>: {url, label, note} } }`。现有 key：`ss_lite, jd_main, zhima_rental, aliyun_cloud_pc, tencent_cloud_pc, tencent_cloud_server, compshare, autodl, runpod, jd_monitor, jd_keyboard, cmb_card, wildcard, apple_gift_card`；其中已填链接：ss_lite、jd_main、tencent_cloud_server、compshare、cmb_card。

## 5. 规则

- 用词：页面上只说「推荐」，不出现「推广」。
- 空链接推荐位隐藏：`.offer[hidden]{display:none}`。
- 每次 build 幂等：链接替换与支持块注入都可重复执行。
- 内容边界：不建地址生成器、不提供假身份信息；不编造价格与套餐。

## 6. 曝光（`.github/promo/`）

已自动完成：站长验证、sitemap、长尾标题、结构化数据、OG 图、分享条。需人工：Bing / Google 提交、LinuxDo、微博、V2EX 发帖（文案在对应 md）、GitHub About、微信群转发。知乎只发不敏感的「租电脑」页；小红书已因「引导站外」被限流，文案保留但不建议再发。

## 7. 验证与排查

- `python3 tools/build.py` 日志：`guides/<id>: 推荐位 N 个已填 · M 个隐藏`。
- 状态页无此模块的健康行（纯静态）；GoatCounter 看板看 `aff/*` 点击。
- 手机溢出检查：指南页曾因两张收款码各 58vw 撑开网格，现为各 38vw 并允许换行。

## 8. 已知问题

1. 京东链接 `jd_main` 指向的商品未确认。
2. 阿里云云大使、腾讯云 GPU 推广者、RunPod、AutoDL 等推荐链接空缺。
3. 评论区未启用。
4. 没有独立域名，AdSense 类广告暂不可行。

## 9. 待办

1. 补齐推荐链接（等站长提供）。
2. 第四步候选：Claude / Gemini 订阅、Cursor 等工具的同一路径复用。
3. 每页顶部加「最后核对日期」与「价格可能变化」的一句话。
4. 读者反馈：评论区启用后在每页末尾加「哪一步卡住了」引导语。

## 10. 常见改动去哪改

| 想做什么 | 改哪里 |
|---|---|
| 换 / 加推荐链接 | `guides/links.json`；页面里放 `<div class="offer" data-aff="key">` 或 `<a data-aff="key">` |
| 加一篇指南 | `guides/guides.json` 加项；复制一页 HTML 改内容；确保有 `build:header / analytics / comments / guide-support / jsonld` 标记 |
| 改支持块文案或收款码 | `apply_guide_support`；图片在 `assets/` |
| 改 HowTo 步骤来源 | `render_guide_jsonld` 读的是 `<ol class="steps">`，`steps-alt` 不算 |
