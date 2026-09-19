# 新笔记模板

复制这个目录来创建新的静态笔记页：

```bash
cp -R templates/note notes/my-new-note
```

然后修改：

- `notes/my-new-note/index.html`：标题、description、og:url / canonical 里的 slug、正文
- `notes/my-new-note/styles.css`：只补本篇需要的排版；颜色一律用 `site.css` 的变量
- `notes/notes.json`：追加一项（`updated` 决定排序）

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

## 不要删的东西

模板里这几段是站点框架的接口，删掉就没有统一页头、深浅色开关和访问统计：

- `<link rel="stylesheet" href="../../site.css" />` 和 `<head>` 里那段读 `localStorage.theme` 的脚本
- `<!-- build:header -->` / `<!-- build:site-name -->` / `<!-- build:comments -->` / `<!-- build:analytics -->`
  四对标记，内容由 `tools/build.py` 注入，标记之外随便改
- `<script src="../../site.js" defer></script>`

## 发布

```bash
python3 tools/build.py            # 重新生成列表、RSS、sitemap，并注入页头页脚
python3 -m unittest discover -s tests
git checkout -b notes/my-new-note
git add -A && git commit -m "notes: 新增 xxx"
git push -u origin notes/my-new-note   # 然后开 PR，squash 合到 master
```

改动走分支 + PR，不直接推 master（见 `docs/prd/site.md` §2）。

## 手机端自检

`docs/prd/site.md` 要求 340 / 360 / 390 / 430px 下 `document.documentElement.scrollWidth` 不超过视口。
最常见的溢出来源是不换行的长代码行和宽表格：代码块本身已经 `overflow-x: auto`，表格请包在 `.table-wrap` 里。
