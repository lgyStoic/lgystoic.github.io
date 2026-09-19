# PRD：笔记（/notes/）

> 内容索引 `notes/notes.json`；每篇笔记 `notes/<slug>/index.html` + 自带 `styles.css`；起步模板 `templates/note/`；列表由 `tools/build.py` 生成。

## 1. 目标与非目标

**目标**：存放课程、论文、性能实验的整理，写给半年后的自己看；推导、数字、失败的尝试都保留。每篇是独立的静态页，样式互不影响。

**非目标**：不用 Markdown 转换器或博客框架；不做评论以外的互动；不追求发布频率。

## 2. 约束

- 每篇笔记自包含（HTML + CSS），不依赖站点 CSS 以外的公共资源；页头页脚通过 build 标记注入。
- 列表、首页「最新笔记」、主题标签、RSS、sitemap 全部由 `notes.json` 生成，**不要手改列表 HTML**。
- 原创研究类笔记（如深圳住房）含大量数据表，需注意手机端表格横滑。

## 3. 功能清单

| 功能 | 说明 | 代码 |
|---|---|---|
| 首页最新笔记 | 最新 6 篇 + 主题标签（常用标签直接摆出，长尾折进 `<details>`） | `render_latest`、`render_topic_links` |
| 归档页 | 按年分组；关键词搜索（标题 / 摘要 / 标签）；标签 chips 筛选；`/` 键聚焦；结果计数与空状态 | `render_archive`、`render_tag_filters`、`site.js archive()` |
| 单篇页 | 模板含标题、来源、更新时间、TL;DR、正文；`featured` 在列表上加星；`status` 显示已发布 / 草稿 | `templates/note/` |
| RSS | `feed.xml`（RSS 2.0） | `build.py` |
| 分享卡 | `assets/og/notes.png` 作为列表页 OG 图 | 各页 head |

## 4. 数据模型 `notes/notes.json`

数组，每项：`title, slug, url("./notes/<slug>/"), absoluteUrl("/notes/<slug>/"), source, tags[], summary, status("已发布"|"草稿"), featured(bool), updated(YYYY-MM-DD)`。按 `updated` 倒序渲染。

## 5. 新增一篇（流程）

```bash
cp -R templates/note notes/<slug>
# 编辑 notes/<slug>/index.html、styles.css；在 notes/notes.json 追加一项
python3 tools/build.py
```

## 6. 验证与排查

- `python3 tools/build.py` 后检查 `notes/index.html`、`index.html`、`feed.xml`、`sitemap.xml` 都出现新篇。
- 新页面必须带 `<!-- build:header -->`、`<!-- build:site-name -->`、`<!-- build:analytics -->` 标记，否则没有统一页头和统计。
- 手机溢出检查见 site.md。

## 7. 已知问题

1. 模板目录 `templates/note/` 本身会被 Pages 发布出去（已用 robots 屏蔽，未加 noindex，避免复制时把 noindex 带进正文）。
2. 没有标签页（按标签聚合的独立 URL），标签只在归档页做前端筛选。
3. 旧数据笔记里的 JSON 表格文件（如 `table_deep.json`）也在仓库里公开。

## 8. 待办

1. 「我读过的」：给 `notes.json` 加 `kind: read`，首页分开显示，来源可来自收件箱摘要。
2. 标签独立页（静态生成，利于搜索引擎）。
3. 笔记内目录（TOC）与阅读时长的模板支持。
4. 把 Markdown 写作 → HTML 的转换脚本放进 `tools/`，仍然输出自包含 HTML。

## 9. 常见改动去哪改

| 想做什么 | 改哪里 |
|---|---|
| 改首页展示篇数 | `render_latest` |
| 改标签折叠阈值 | `render_tag_filters(primary=10)`、`render_topic_links(limit=14)` |
| 改模板 | `templates/note/index.html`、`styles.css`、`README.md` |
| 改搜索匹配字段 | `render_archive` 里的 `data-search` 内容 + `site.js archive()` |
