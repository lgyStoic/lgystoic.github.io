# 任务：给 9 篇旧笔记补统一页头（接入站点框架）

> 写给接手的 agent，自包含。核对日期：2026-09-19（master `a86f9f5` 之后）。读完这份再读仓库里的 PRD，不要凭印象动手。

## 0. 先读这些，按顺序

1. 根目录 `CLAUDE.md` 与 `docs/prd/agent.md`：本仓库给 agent 的总规则，最高优先级；本文档与它冲突时听它的。
2. `docs/prd/README.md`：站点级共同约束（手机 340–430px 不能横向溢出、纯静态、无第三方脚本）。
3. `docs/prd/notes.md` §2 / §5 / §7：笔记页的约束、新增流程、已知问题（§7 第 4 条就是本任务）。
4. `docs/prd/site.md` §2（发布流程：分支 + PR squash 合到 master，不直推）与 §3（统一页头注入机制、SEO 要求）。
5. `templates/note/index.html` + `styles.css` + `README.md`：正确形态的模板，以它为准。
6. `notes/home-camera-vlm-pipeline/`：已按模板接好的一篇真实笔记，直接对照。

## 1. 目标与非目标

**目标**：下面 9 篇每一篇都做到

- `<head>` 里引 `../../site.css`（在本篇样式之前）+ 模板里那段读 `localStorage.theme` 的主题引导脚本（照抄，一字不改）。
- 五对 build 标记齐全：`header` / `site-name` / `jsonld` / `comments` / `analytics`（`jsonld` 已由 #114 加好，其余四对要补）。
- 删掉各篇手写的 `<header class="topbar">` 之类页头，改由 `<!-- build:header -->` 注入。
- 页尾用 `<footer class="site-footer">`（照模板），`<script src="../../site.js" defer>`。
- `<title>xxx | Anaxagore</title>`、description（与 `notes.json` 的 summary 一致）、canonical、`og:*`、`twitter:card`；`og:image` 用 `https://lgystoic.github.io/assets/og/notes.png`。
- 颜色改走 `site.css` 的变量（`--bg --bg-tint --surface --ink --ink-soft --muted --line --line-soft --accent --accent-soft`，页宽 `--page` = 44rem），深浅色切换时整页一致，不能出现「页头变黑、正文还是白」。
- 340 / 360 / 390 / 430px 视口下 `document.documentElement.scrollWidth` 不超过视口。

**非目标**（做了会被打回）：

- 不重排版式、不改正文内容、不改文件名和 slug。
- 不改 `site.css`、`site.js`、`tools/build.py`。
- 不手改 `notes/index.html`、`index.html`、`feed.xml`、`sitemap.xml`、`llms.txt`（由 `build.py` 生成；跑完 build 把它们一起提交即可）。
- 不动 `radar/`、`guides/`、`status/`。
- `notes/notes.json` 不需要改；如果非要改，保持现有格式（tags 单行），不要用 `json.dumps` 整体重写。

## 2. 现状审计（2026-09-19 用脚本重新核过）

| slug | 体量 | 样式 | 手写页头 | `<main>` | 现有标记 | 与 site.css 撞名的 class |
|---|---|---|---|---|---|---|
| 2026-08-10-shenzhen-metro-200m | 128 KB | 内联 | 无 | 无 | jsonld | badge card warn |
| 2026-08-17-metro200m-residential-profile | 1328 KB | 内联 | 无 | 无 | jsonld | badge sub warn wrap |
| kernel-design-agents-skills | 16 KB | styles.css | 有 | 有 | jsonld | brand brand-mark section section-head |
| mit-6s184-flow-diffusion | 26 KB | styles.css | 有 | 有 | jsonld | brand brand-mark empty-state section section-head |
| pytorch-autograd-notes | 23 KB | 内联 | 有 | 有 | jsonld | site-nav wrap |
| ring-collectives | 31 KB | 内联 | 有 | 无 | jsonld | primary site-nav table-wrap |
| swiglu-mlp-drop-h | 22 KB | 内联 | 无 | 有 | jsonld | warn |
| swiglu-mlp-forward-backward-optimization | 18 KB | 内联 | 有 | 有 | jsonld | badge |
| swiglu-packed-save-factors | 17 KB | 内联 | 无 | 有 | jsonld | （无） |

每篇动手前先用这段重新核对撞名：

```bash
python3 - ring-collectives <<'PY'
import re,sys
site=open('site.css').read(); sc=set(re.findall(r'\.([a-zA-Z_][\w-]*)\s*[{,:\s]',site))
for slug in sys.argv[1:]:
    h=open(f'notes/{slug}/index.html',encoding='utf-8').read()
    try: h+=open(f'notes/{slug}/styles.css').read()
    except FileNotFoundError: pass
    own=set(re.findall(r'\.([a-zA-Z_][\w-]*)\s*[{,]',h))
    print(slug, sorted(c for c in own&sc if c!='site-footer'))
PY
```

「撞名」= 本篇 CSS 定义了 site.css 里也有的同名 class。引入 site.css 后两边规则叠加：后加载的（本篇）覆盖同名属性，但 site.css 里本篇没写的属性会额外生效。最要命的几个：

- `.section`：site.css 给它 `padding-block: 34px; border-bottom: 1px solid var(--line-soft)`，本篇若也画了分隔线就是双线、双倍内边距（#115 里踩过）。
- `.wrap`：site.css 给它 `width: min(var(--page), 100%); margin: 0 auto; padding-inline: 22px; overflow-wrap: anywhere`，会把本篇原本的容器压到 704px。
- `.site-nav` / `.brand` / `.brand-mark`：统一页头自己用的 class，本篇同名会把注入的页头样式搞坏。
- `.table-wrap`：site.css 是 `overflow-x: auto; margin-top: 10px`；ring-collectives 自己也定义了，先看两边是否一致再决定是否改名。
- `badge / card / warn / sub / primary / empty-state / section-head`：影响较小，逐个看。

已知溢出（`python3 tools/check_mobile.py --all` 2026-09-19 结果）：`swiglu-mlp-drop-h` 在四个宽度下 scrollWidth 都是 832，撑开的是一张 `table`（最宽元素报告为「path…」那张），必须包 `table-wrap`；其余 8 篇目前不溢出，改完后不能变差。

**处理原则：改本篇的类名（加前缀，如 `.kd-section`、`.pt-wrap`），不改 site.css。** 全站 20 多个页面共用 site.css。

## 3. 每篇的操作清单

按顺序，做完一步验一步：

1. `cp` 一份原文件备用，改完 `diff` 确认只动了外壳。
2. **先处理撞名**：在本篇 HTML + CSS 里把第 2 节列出的 class 统一改名（`class="..."` 与 CSS 选择器同步），再引 site.css。顺序不能反，否则分不清哪些变化是撞名造成的。
3. `<head>`：`<title>xxx | Anaxagore</title>`；补 description / og / twitter / canonical（照模板抄，换 slug）；在本篇样式之前加 `<link rel="stylesheet" href="../../site.css" />`；加主题引导脚本；保留 `<!-- build:jsonld --><!-- /build:jsonld -->`。
4. `<body>`：删手写页头，换成 `<!-- build:header --> <!-- /build:header -->`；没有 `<main>` 的把正文包进 `<main>`（**不要加 `wrap` class**，会被压到 704px，除非这篇本来就是窄栏排版）；`</main>` 前加 `<!-- build:comments --><!-- /build:comments -->`；`</body>` 前加 `<footer class="site-footer">…</footer>`（照模板）、`<script src="../../site.js" defer></script>`、`<!-- build:analytics --><!-- /build:analytics -->`。
5. **颜色改走变量**：本篇 CSS 的 `:root { --xxx: #… }` 常与 site.css 同名但值不同。删掉本篇的 `:root` 色值定义让它吃 site.css 的；本篇独有的颜色（某个 teal、blue）新定义带前缀的变量，并在 `[data-theme="dark"]` 和 `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) … }` 两处给深色值（写法照 `site.css` 第 30–60 行）。十六进制色值不能直接留在规则里，否则深色模式下就是一块白。
6. **手机溢出**：`pre` 要 `overflow-x: auto`；宽表格外面包 `<div class="table-wrap">`；grid / flex 里的容器加 `min-width: 0`（默认 `min-width: auto` 会被不换行的长代码行撑开整条轨道，最常见的溢出来源）。
7. `python3 tools/build.py`，然后跑第 4 节的检查。
8. `python3 -m pytest -q tests`。

## 4. 验证（每篇都要跑，结果贴进 PR）

### 4.1 标记是否真的被注入、结构化数据没改坏

```bash
python3 - notes/<slug>/index.html <<'PY'
import re,sys,json
h=open(sys.argv[1],encoding='utf-8').read()
for k in ('header','site-name','analytics','jsonld','comments'):
    m=re.search(rf'<!-- build:{k} -->(.*?)<!-- /build:{k} -->',h,re.S)
    print(f'{k:10s}', 'missing' if not m else f'{len(m.group(1).encode())} 字节')
for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>',h,re.S): json.loads(m)
print('ld+json ok')
PY
```

期望（以 `home-camera-vlm-pipeline` 为参照）：header ≈ 770 字节、site-name ≈ 15、analytics ≈ 1130、jsonld ≈ 1100；comments 在 `site.json` 填好 giscus id 之前是 6 字节（只有换行），**这是正常的**。

### 4.2 手机宽度不溢出（首选 Playwright）

```bash
python3 -m pip install -q playwright        # 沙箱已预装浏览器，不要 playwright install
python3 tools/check_mobile.py notes/<slug>/index.html      # 默认 340/360/390/430
python3 tools/check_mobile.py --all                        # 全站代表页 + 全部笔记
```

期望每行 ✓。溢出时脚本会打印「最宽元素」是谁撑的；`pre` 里的代码行超出自己的滚动容器不算，脚本已排除。

**不要用桌面 headless Chrome 的 `--window-size=390` 截图或量宽**：它把布局视口钳在约 485–500px，`<meta viewport>` 也不起作用，截图是裁出来的；经典滚动条还占 15px 宽。Playwright 装不上时，用同源 iframe 固定宽度再量：

```bash
python3 - notes/<slug>/index.html <<'PY'
import sys,pathlib
slug=pathlib.Path(sys.argv[1]).parent.name
frames=''.join(f'<iframe id="f{w}" src="/notes/{slug}/" style="width:{w}px;height:600px;border:0;display:block" scrolling="no"></iframe>' for w in (340,360,390,430))
html=('<!doctype html><meta charset=utf-8><body style="margin:0">'+frames+'<pre id=out></pre><script>addEventListener("load",()=>{const o=[];for(const w of [340,360,390,430]){const d=document.getElementById("f"+w).contentDocument;o.push(w+" scrollWidth="+d.documentElement.scrollWidth)}document.getElementById("out").textContent=o.join("\\n")})</script>')
pathlib.Path('_harness_tmp.html').write_text(html,encoding='utf-8')
print('python3 -m http.server 8765 后打开 http://localhost:8765/_harness_tmp.html，读完删掉 _harness_tmp.html')
PY
```

`_harness_tmp.html` 用完必须删，`git status` 里不能出现它。

### 4.3 深浅色都看一眼

```bash
python3 - notes/<slug>/index.html <<'PY'
import sys,pathlib
from playwright.sync_api import sync_playwright
p=pathlib.Path(sys.argv[1]).resolve()
with sync_playwright() as pw:
    b=pw.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome',args=['--no-sandbox'])
    for theme in ('light','dark'):
        pg=b.new_page(viewport={'width':390,'height':1200},color_scheme=theme); pg.goto(p.as_uri()); pg.wait_for_timeout(200)
        bg=pg.evaluate("[getComputedStyle(document.body).backgroundColor, getComputedStyle(document.querySelector('main')||document.body).backgroundColor, getComputedStyle(document.querySelector('.site-header')||document.body).backgroundColor]")
        print(theme,'body/main/header 背景:',bg); pg.screenshot(path=f'/tmp/{p.parent.name}-{theme}.png'); pg.close()
    b.close()
PY
```

期望：深色下三个背景都是深色（不是 `rgb(255, 255, 255)`），截图肉眼看一遍无白块。

## 5. 交付

- 一篇一个 commit（标题 `notes: <slug> 接入站点框架`），可以合成一个 PR；PR 描述里贴每篇 4.1 / 4.2 的输出。
- 合并后 `docs/prd/notes.md` §7 第 4 条删掉，并在 §6 加一句「所有笔记页已带五对标记」。
