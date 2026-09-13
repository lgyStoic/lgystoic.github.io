# Garry 的学习站

纯静态个人站，放课程笔记、性能实验、论文整理和数据研究。没有框架、没有构建依赖，
GitHub Pages 直接托管仓库根目录。

## 结构

```text
index.html        首页：自我介绍 + 最新 6 篇 + 主题标签
notes/index.html  归档页：按年分组 + 关键词搜索 + 标签筛选
notes/notes.json  唯一的内容索引（所有列表都由它生成）
notes/<slug>/     每篇笔记，自带样式，互不影响
site.css site.js  站点样式与交互（深浅色、搜索、筛选）
tools/build.py    从 notes.json 与 radar/data 生成列表 HTML、feed.xml、sitemap.xml
tools/radar.py    AI 信息雷达：抓 RSS → 去重 → 打分 → （可选）AI 摘要
tools/inbox.py    私有收件箱：读取私有仓库 Issue 里手动投递的链接，整理成每日摘要
radar/            雷达页、信息源配置（sources.json）、每日数据（data/）、每期永久链接
templates/note/   新笔记的起步模板
```

列表是**预渲染进 HTML** 的，不是前端 fetch 出来的：搜索引擎和社交卡片能抓到内容，
禁用 JS 也能正常读。JS 只负责深浅色切换和归档页的搜索/筛选。

## 本地预览

```bash
python3 -m http.server 8765
# http://localhost:8765/
```

## 添加新笔记

1. 复制模板并写内容：

```bash
cp -R templates/note notes/my-new-note
```

2. 在 `notes/notes.json` 追加一条元数据（`updated` 决定排序）：

```json
{
  "title": "新笔记标题",
  "slug": "my-new-note",
  "url": "./notes/my-new-note/",
  "absoluteUrl": "/notes/my-new-note/",
  "source": "课程或论文来源",
  "tags": ["tag-1", "tag-2"],
  "summary": "一句话说明这篇笔记讲什么。",
  "status": "已发布",
  "featured": false,
  "updated": "2026-09-13"
}
```

3. 重新生成列表、RSS 和 sitemap：

```bash
python3 tools/build.py
```

4. 提交推送：

```bash
git add . && git commit -m "Add my new note" && git push origin master
```

> 脚本只改写页面里 `<!-- build:xxx -->` 到 `<!-- /build:xxx -->` 之间的内容，
> 标记之外的排版随便改，重跑不会被覆盖。`featured` 字段目前不影响首页，
> 首页展示的是最近更新的 6 篇。

## AI 信息雷达

`/radar/` 是每天自动生成的信息简报。流程全部跑在 GitHub Actions 里
（`.github/workflows/radar.yml`，北京时间每天 08:00，也可在 Actions 页手动触发）：

```text
radar/sources.json  →  tools/radar.py  →  radar/data/<date>.json  →  tools/build.py  →  radar/<date>/
   信息源 + 规则         抓取/去重/打分          当天数据                 渲染页面 + RSS
```

- **信息源**：`radar/sources.json` 的 `sources`。每个源有 `category`、`weight`（0-3，越高越容易进「必看」），
  噪音大的源加 `"require_topic": true`，只保留命中 `topic_keywords` 的条目。
- **规则**：`high_keywords` 命中标题 +2 分，`topic_keywords` 每命中一个 +1（最多 +2），`mute_keywords` −3。
  ≥4 必看，2-3 值得看，其余折叠。
- **去重**：`radar/data/seen.json` 记录 120 天内出现过的链接，跨天不重复。
- **AI 摘要**：仓库 Secrets 里配置 `ANTHROPIC_API_KEY`（Claude，优先）或 `GEMINI_API_KEY`（Gemini，默认 `gemini-pro-latest`，配额不足时自动降级 `gemini-flash-latest`）后自动启用，
  负责优先级判断、中文一句话摘要和「为什么值得看」。都没有时退回关键词规则，摘要取原文前 160 字。
  AI 环节任何失败都退回规则，不会让整次运行挂掉。
- **补漏 / 冷启动**：Actions 页手动触发时填 `window_hours`（如 168）可抓过去一周；同一天多次运行会合并进当天文件，不会重复。
- **本地试跑**：`python3 tools/radar.py --dry-run` 只打印不落盘；`python3 tools/radar.py && python3 tools/build.py` 生成完整页面。

## 私有收件箱（小红书 / 微信 / 任意没有 RSS 的链接）

小红书这类平台没有可靠的抓取通道，改用「看到就投递」：手机分享 → iOS 快捷指令 → 私有仓库 Issue 评论。
每天的雷达运行顺手整理，**数据只存在私有仓库**，不会出现在这个公开站点上。

一次性配置：

1. 在 GitHub 新建一个**私有**仓库 `radar-inbox`（空仓库即可，勾上 README 也行）。
2. 建一个 fine-grained personal access token：Repository access 只选 `radar-inbox`，
   权限给 **Issues: Read and write** 与 **Contents: Read and write**。
3. 把 token 存到本仓库 Settings → Secrets → Actions → `INBOX_TOKEN`
   （仓库名不是 `lgyStoic/radar-inbox` 的话再加一个 Variable `INBOX_REPO`）。
4. 在 Actions 页手动跑一次「AI 信息雷达」：脚本会自动在私有仓库里创建「📥 雷达收件箱」Issue、
   README（含快捷指令配置步骤）和 `state.json`。
5. 按私有仓库 README 里的说明配好 iOS 快捷指令（同一个 token）。

之后每天 08:00：新评论 → 取页面标题/描述（小红书通常取不到，就用你写的备注）→ AI 摘要 →
写入私有仓库 `digest/<日期>.md`，README 维护最近 30 条索引，处理过的评论点 👍。

## 发布

GitHub Pages：Deploy from a branch，`master` 分支，`/ (root)` 目录，
线上地址 <https://lgystoic.github.io/>。

## 来源与版权提醒

MIT 6.S184 页面是个人学习整理，原课程网站是 <https://diffusion.csail.mit.edu/>。
公开发布时请保留来源说明；不确定课程图表是否允许转载的，建议换成自己的图解或只留文字总结。
