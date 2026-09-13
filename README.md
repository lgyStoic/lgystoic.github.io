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
tools/build.py    从 notes.json 生成列表 HTML、feed.xml、sitemap.xml
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

## 发布

GitHub Pages：Deploy from a branch，`master` 分支，`/ (root)` 目录，
线上地址 <https://lgystoic.github.io/>。

## 来源与版权提醒

MIT 6.S184 页面是个人学习整理，原课程网站是 <https://diffusion.csail.mit.edu/>。
公开发布时请保留来源说明；不确定课程图表是否允许转载的，建议换成自己的图解或只留文字总结。
