# 新笔记模板

复制这个目录来创建新的静态笔记页：

```bash
cp -R templates/note notes/my-new-note
```

然后修改：

- `notes/my-new-note/index.html`
- `notes/my-new-note/styles.css`
- `notes/notes.json`

`notes/notes.json` 示例：

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
