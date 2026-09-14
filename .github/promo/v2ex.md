# V2EX · 分享创造

**标题**：做了一个跑在 GitHub Pages 上的个人平台：每日 AI 雷达 + 深圳活动清单 + 离职上手指南

**正文**：

离职之后没服务器没域名，想给自己搭一套「记 / 看 / 做」的个人平台，就全压在 GitHub 上了：

- **每日雷达**：29 个源（OpenAI、DeepMind、HF Papers、PyTorch、Qwen、几位博主、GitHub Releases 等）每天 08:00 由 Actions 抓一遍，去重后交给模型排优先级、写一句话摘要，生成静态页和 RSS。模型不可用时退化成规则。
- **活动清单**：深圳 / 广州 / 香港的 AI 聚会、黑客松、比赛，从活动行、lu.ma、公众号搜索等 50 多个源抓，按日期排。
- **上手指南**：三页，租电脑 → 代理软件 → 注册 ChatGPT，写给刚离职想开始用 AI 工具的人。
- **状态页**：每个源的健康度、失败连击、自动禁用，Actions 定时巡检。

全静态 HTML + 一个 Python 构建脚本，没有框架。源码公开。

站：https://lgystoic.github.io/?utm_source=v2ex
仓库：https://github.com/lgyStoic/lgystoic.github.io

想听听大家：信息源还缺哪些？活动源有什么一手渠道？
