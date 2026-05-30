# Garry 的学习站

一个纯静态个人知识站，适合放课程笔记、PDF 整理、论文阅读和概念地图。当前内容：

- `notes/mit-6s184-flow-diffusion/`：MIT 6.S184 Flow Matching 与 Diffusion Models 中文学习页

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

1. 在 `notes/` 下新增一个目录，例如 `notes/my-new-note/`。
2. 放入该笔记的 `index.html`、`styles.css`、资源文件等。
3. 在根目录 `index.html` 的「已整理内容」区域新增一张卡片。

## 来源与版权提醒

当前 MIT 6.S184 页面是个人学习整理，原课程网站是：

- https://diffusion.csail.mit.edu/

如果公开发布，建议在页面中保留来源说明；如果不确定课程图表是否允许转载，最好把抽取自 PDF 的原图替换为自己的图解或只保留文字总结。
