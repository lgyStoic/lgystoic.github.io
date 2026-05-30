# Garry 的学习站

一个纯静态个人知识站，适合放课程笔记、PDF 整理、论文阅读和概念地图。当前内容：

- `notes/mit-6s184-flow-diffusion/`：MIT 6.S184 Flow Matching 与 Diffusion Models 中文学习页
- `notes/notes.json`：所有笔记的索引数据，首页和 `/notes/` 会读取它渲染卡片
- `templates/note/`：新增笔记时可复制的起步模板

## 本地预览

在当前目录运行：

```bash
python3 -m http.server 8765
```

然后打开：

```text
http://localhost:8765/
```

## GitHub Pages 发布

这个仓库已经是个人主页仓库：

```text
https://lgystoic.github.io/
```

当前 Pages 配置：

- Source: Deploy from a branch
- Branch: `master`
- Folder: `/ (root)`

## 添加新笔记

1. 复制模板：

```bash
cp -R templates/note notes/my-new-note
```

2. 修改新目录里的页面内容：

```text
notes/my-new-note/index.html
notes/my-new-note/styles.css
```

3. 在 `notes/notes.json` 中追加一条元数据：

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
  "updated": "2026-05-30"
}
```

4. 提交并推送：

```bash
git add .
git commit -m "Add my new note"
git push origin master
```

如果想让某篇笔记出现在首页，把该条记录的 `featured` 改成 `true`。

## 来源与版权提醒

当前 MIT 6.S184 页面是个人学习整理，原课程网站是：

- https://diffusion.csail.mit.edu/

如果公开发布，建议在页面中保留来源说明；如果不确定课程图表是否允许转载，最好把抽取自 PDF 的原图替换为自己的图解或只保留文字总结。
