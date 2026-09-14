# 曝光计划（Anaxagore · lgystoic.github.io）

目标：让「上手指南」三页被搜到、被转发，接下来靠推荐位（CPS）赚钱。
站点本身没有服务器、没有域名，所以曝光只能靠三件事：搜索引擎收录、外部平台发帖、读者转发。

## 已由构建自动完成
- Bing / Google 站长验证已加，sitemap 已提交入口：`https://lgystoic.github.io/sitemap.xml`
- 三页标题改成长尾搜索词；HowTo + 面包屑结构化数据；robots.txt
- 每页 1200×630 分享卡片（`/assets/og/*.png`），微信 / 小红书 / X / 知乎粘链接时带图
- 指南页底部「复制链接 / 分享…」按钮

## 需要你亲手做的（按收益 / 风险排序）

原则：**敏感内容只留在自己站上，往外发只发不敏感的那一页，搜索引擎负责把有需求的人送进来。**
「代理」「注册 ChatGPT」在知乎、小红书属于限流题材，硬发没效果还伤账号。

| 序 | 平台 | 动作 | 文案 | 风险 | 用时 |
|---|---|---|---|---|---|
| 1 | Bing 站长工具 | 「站点地图」提交 sitemap；「URL 提交」三页 | — | 无 | 5 分钟 |
| 2 | Google Search Console | 提交 sitemap；三页「请求编入索引」 | — | 无 | 5 分钟 |
| 3 | LinuxDo（linux.do） | 发一帖介绍整个站，代理 / ChatGPT 话题在那里是日常 | `linuxdo.md` | 低 | 10 分钟 |
| 4 | 微博 | 发一条带链接的图文（正文允许网址） | `weibo.md` | 低 | 10 分钟 |
| 5 | V2EX | 「分享创造」发一帖 | `v2ex.md` | 低 | 10 分钟 |
| 6 | GitHub | 仓库 About 填站点地址，加 topics | — | 无 | 2 分钟 |
| 7 | 微信 | 转到 2–3 个求职群、AI 学习群 | — | 低 | 随手 |
| 5b | 知乎 | 回答「离职后租电脑」类问题（回答 0），文末带链接 | `zhihu.md` 回答 0 | 低 | 15 分钟 |
| — | 知乎另两条（代理 / ChatGPT） | **先不发** | `zhihu.md` | 高 | — |
| ✕ | 小红书 | **不可用**。2026-09-14 第 1 篇即被判「引导站外」：提平台名、写「链接在评论区」都算违规，改措辞绕不过去 | `xiaohongshu.md` 仅存档 | 判罚 | — |

## 追踪
每个平台用自己的 `?utm_source=` 参数，Search Console 和 Bing 里能分开看来源：

| 平台 | 链接 |
|---|---|
| 知乎 | https://lgystoic.github.io/guides/?utm_source=zhihu |
| 微博 | https://lgystoic.github.io/guides/?utm_source=weibo |
| V2EX | https://lgystoic.github.io/guides/?utm_source=v2ex |
| 掘金 | https://lgystoic.github.io/guides/?utm_source=juejin |
| 微信群 | https://lgystoic.github.io/guides/?utm_source=wechat |

站点没有统计脚本。要看访问量，装一个隐私友好的免费统计（例如 GoatCounter，一行 script，无 cookie）——这个可以让 Claude 加。

## 节奏
- 第 1 周：1–4 全做完，看 Search Console 的「效果」里哪页开始有展示。
- 第 2–4 周：每周一条小红书 + 一个知乎回答，围着「ChatGPT 注册」「Clash Verge 教程」两个词打。
- 一个月后：如果日访问过千，花 60 元买域名，接 AdSense；否则继续只做 CPS。
