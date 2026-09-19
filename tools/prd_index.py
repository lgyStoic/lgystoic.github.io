#!/usr/bin/env python3
"""生成 docs/prd/index.html：给人看的站点产品说明总览，带架构图、模块地图、每日时间线。

用法：python3 tools/prd_index.py && python3 tools/build.py
图由 contributions.arch_svg 画（和开源贡献页同一套渲染），不依赖外部 JS。
"""
import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import contributions as c

GH = 'https://github.com/lgyStoic/lgystoic.github.io/blob/master/docs/prd/'

def mods(*names): return [{'module': n} for n in names]

SITE_MODULES = mods('RSS 与 JSON 源', '活动源', '招聘站与 ATS', 'GitHub API', '收件箱 Issue',
                    'radar.yml', 'jobs.yml', 'contributions.yml', 'xhs.yml', 'health.yml',
                    'Gemini · Claude', 'radar 数据 JSON', '私有仓库 radar-inbox', 'build.py',
                    'GitHub Pages 静态页', 'RSS · sitemap · 状态页')
SITE_DIAGRAM = {
    'layers': [
        {'name': '来源', 'modules': 'RSS 与 JSON 源, 活动源, 招聘站与 ATS, GitHub API, 收件箱 Issue'},
        {'name': 'Actions', 'modules': 'radar.yml, jobs.yml, contributions.yml, xhs.yml, health.yml'},
        {'name': 'AI', 'modules': 'Gemini · Claude'},
        {'name': '数据', 'modules': 'radar 数据 JSON, 私有仓库 radar-inbox'},
        {'name': '构建', 'modules': 'build.py'},
        {'name': '前端', 'modules': 'GitHub Pages 静态页, RSS · sitemap · 状态页'},
    ],
    'edges': [
        {'from': 'RSS 与 JSON 源', 'to': 'radar.yml', 'label': '抓取'}, {'from': '活动源', 'to': 'radar.yml', 'label': '活动'},
        {'from': '收件箱 Issue', 'to': 'radar.yml', 'label': '投递'}, {'from': '招聘站与 ATS', 'to': 'jobs.yml', 'label': '岗位'},
        {'from': 'GitHub API', 'to': 'contributions.yml', 'label': 'Issue/源码'},
        {'from': 'radar.yml', 'to': 'Gemini · Claude', 'label': '摘要'}, {'from': 'jobs.yml', 'to': 'Gemini · Claude', 'label': '去重'},
        {'from': 'contributions.yml', 'to': 'Gemini · Claude', 'label': '五章+任务卡'}, {'from': 'xhs.yml', 'to': 'Gemini · Claude', 'label': '文稿+生图'},
        {'from': 'health.yml', 'to': 'radar.yml', 'label': '补跑'},
        {'from': 'radar.yml', 'to': 'radar 数据 JSON', 'label': 'JSON'}, {'from': 'jobs.yml', 'to': 'radar 数据 JSON', 'label': ''},
        {'from': 'contributions.yml', 'to': 'radar 数据 JSON', 'label': ''},
        {'from': 'radar.yml', 'to': '私有仓库 radar-inbox', 'label': '收件箱摘要'}, {'from': 'xhs.yml', 'to': '私有仓库 radar-inbox', 'label': 'posts'},
        {'from': 'radar 数据 JSON', 'to': 'build.py', 'label': '渲染'},
        {'from': 'build.py', 'to': 'GitHub Pages 静态页', 'label': 'HTML'}, {'from': 'build.py', 'to': 'RSS · sitemap · 状态页', 'label': '生成'},
    ],
    'caption': '全站数据流：源 → Actions 定时脚本 →（可选）模型 → 仓库里的 JSON → build.py 预渲染 → Pages 托管。没有服务器，数据文件就是公开 API。',
}

MAP_MODULES = mods('笔记', '上手指南', '每日雷达', '活动清单', '工作机会', '开源贡献路线', '收件箱', '学习文稿', '运行状态', 'site.json 注册表', 'build.py', 'site.css · site.js')
MAP_DIAGRAM = {
    'layers': [
        {'name': '记', 'modules': '笔记, 上手指南'},
        {'name': '看', 'modules': '每日雷达, 活动清单, 工作机会, 开源贡献路线'},
        {'name': '做', 'modules': '收件箱, 学习文稿, 运行状态'},
        {'name': '支撑', 'modules': 'site.json 注册表, build.py, site.css · site.js'},
    ],
    'edges': [
        {'from': '每日雷达', 'to': '活动清单', 'label': '同一轮'}, {'from': '每日雷达', 'to': '学习文稿', 'label': '当天条目'},
        {'from': '每日雷达', 'to': '运行状态', 'label': '自检'}, {'from': '工作机会', 'to': '运行状态', 'label': '源健康'},
        {'from': '开源贡献路线', 'to': '运行状态', 'label': '仓库状态'}, {'from': '收件箱', 'to': '笔记', 'label': '阅读列表(待做)'},
        {'from': 'site.json 注册表', 'to': 'build.py', 'label': '导航/卡片'}, {'from': '上手指南', 'to': '运行状态', 'label': '点击统计'},
    ],
    'caption': '模块地图：三个角色加一层支撑。箭头是数据或运行上的依赖。',
}

CONTRIB_MODULES = mods('plan', 'analyze ×14', 'merge', '仓库详情页', 'reuse_run_id')
CONTRIB_DIAGRAM = {
    'layers': [{'name': '计划', 'modules': 'plan, reuse_run_id'}, {'name': '分析', 'modules': 'analyze ×14'}, {'name': '合并', 'modules': 'merge'}, {'name': '页面', 'modules': '仓库详情页'}],
    'edges': [{'from': 'plan', 'to': 'analyze ×14', 'label': '矩阵(并行 7)'}, {'from': 'analyze ×14', 'to': 'merge', 'label': '产物'},
              {'from': 'reuse_run_id', 'to': 'merge', 'label': '复用旧产物'}, {'from': 'merge', 'to': '仓库详情页', 'label': 'build'}],
    'caption': '开源贡献路线：每个仓库一个分析 job（五章 + 任务卡 + 补卡），合并后渲染；改渲染器时用 reuse_run_id 跳过 Gemini。',
}

def timeline_svg():
    """北京时间的每日 / 每周定时一览。"""
    W, H = 720, 210
    x0, x1 = 60, W - 20
    t0, t1 = 7.5, 10.75
    def X(h): return x0 + (h - t0) / (t1 - t0) * (x1 - x0)
    marks = [
        (7 + 50/60, '雷达 槽1', 'radar.yml', 0), (8 + 20/60, '雷达 槽2', 'radar.yml', 1), (8 + 35/60, '岗位 · 兜底1', 'jobs.yml · health.yml', 0),
        (9 + 10/60, '学习卡片', 'xhs.yml', 1), (9 + 40/60, '岗位周报', '周一 xhs.yml', 0), (9 + 20/60, '开源贡献', '周一全量 / 周四重点', 0), (10 + 5/60, '雷达 槽3', 'radar.yml', 1), (10 + 20/60, '兜底2', 'health.yml', 0),
    ]
    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="每日定时时间线">']
    y = 110
    out.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" class="d-edge" style="opacity:.5"/>')
    for h in (8, 9, 10):
        out.append(f'<line x1="{X(h):.0f}" y1="{y-6}" x2="{X(h):.0f}" y2="{y+6}" class="d-edge"/>' + c._svg_text(X(h), y + 22, f'{h:02d}:00', 'd-sub'))
    for h, name, sub, up in marks:
        x = X(h); hhmm = f'{int(h):02d}:{int(round((h % 1) * 60)):02d}'
        out.append(f'<circle cx="{x:.0f}" cy="{y}" r="5" class="d-num"/>')
        if up == 0:
            out.append(f'<line x1="{x:.0f}" y1="{y-8}" x2="{x:.0f}" y2="{y-30}" class="d-edge" style="opacity:.5"/>')
            out.append(c._svg_text(x, y - 66, hhmm, 'd-elabel') + c._svg_text(x, y - 50, name, 'd-step') + c._svg_text(x, y - 35, sub, 'd-sub'))
        else:
            out.append(f'<line x1="{x:.0f}" y1="{y+8}" x2="{x:.0f}" y2="{y+34}" class="d-edge" style="opacity:.5"/>')
            out.append(c._svg_text(x, y + 50, hhmm, 'd-elabel') + c._svg_text(x, y + 68, name, 'd-step') + c._svg_text(x, y + 84, sub, 'd-sub'))
    out.append('</svg>')
    return f'<figure class="diagram"><div class="diagram-wrap arch">{"".join(out)}</div><figcaption>北京时间。雷达三个槽加两次兜底，是为了避开 GitHub 整点丢任务；当天已有任何一次运行就不重复。</figcaption></figure>'

MODULES = [
    ('site', '站点框架', '注册表、注入机制、页头 / 统计 / 评论、SEO、工作流通用规则、共用的 AI 调用层'),
    ('notes', '笔记', 'notes.json 索引、自包含页面、归档搜索、RSS'),
    ('guides', '上手指南', '租电脑 → 代理 → ChatGPT 三步；推荐位注册表；曝光计划'),
    ('radar', '每日雷达', '二十多个源 → 去重打分 → 模型摘要 → 必看 / 值得看 / 其余'),
    ('events', '活动清单', '五种源解析器 → 模型抽字段 → 深圳 / 广州 / 香港 / 线上'),
    ('jobs', '工作机会', '19 个官方源 + 猎聘 / ATS 适配器 → 可解释匹配 → 深圳优先'),
    ('contributions', '开源贡献路线', '14 个仓库五章分析 + 无 GPU 可做的任务卡 + 架构图'),
    ('inbox', '收件箱', '手机投递到私有仓库 Issue → 每日摘要'),
    ('xhs', '小红书文稿', '每日学习卡片（雷达条目 → 标题/正文/标签 + 封面）；周一岗位精选（jobs.json → 12 个真实公司岗位 + 封面）'),
    ('status', '运行状态 · 巡检', '最近一次运行、巡检报告、四栏源健康表、自动停用与兜底'),
]

PIPELINES = [
    ('每日雷达', 'radar/sources.json', 'tools/radar.py', 'radar/data/<日期>.json', '/radar/、/radar/<日期>/、radar/feed.xml'),
    ('活动清单', 'radar/event_sources.json', 'tools/events.py', 'radar/data/events.json', '/radar/events/'),
    ('工作机会', 'radar/job_sources.json、ats_companies.json', 'tools/jobs.py + 3 个适配器 + jobs_ai.py', 'radar/data/jobs.json', '/radar/jobs/'),
    ('开源贡献', 'radar/contribution_repos.json', 'tools/contributions.py', 'radar/data/contributions.json', '/radar/contributions/、每仓库一页'),
    ('收件箱 / 文稿', '私有仓库 Issue、当天雷达', 'tools/inbox.py、tools/xhs.py', '私有仓库 digest/、posts/', '（私有）'),
    ('巡检', 'radar/data/*.json 的 sources', 'tools/check.py、health.yml', 'radar/data/health.json、radar/checks/*.md', '/status/'),
    ('笔记 / 指南', 'notes/notes.json、guides/*.json', 'build.py', '—', '/notes/、/guides/'),
]

def main():
    css = re.search(r'\.diagram\{\{.*?(?=@media \(max-width:560px\))', c.detail_page.__code__.co_consts[0] if False else open(ROOT / 'tools/contributions.py', encoding='utf-8').read(), re.S).group(0).replace('{{', '{').replace('}}', '}')
    cards = ''.join(f'<article class="prd-card"><h3><a href="{GH}{k}.md" rel="noopener">{n}</a></h3><p>{b}</p></article>' for k, n, b in MODULES)
    rows = ''.join(f'<tr><td><b>{m}</b></td><td>{s}</td><td><code>{t}</code></td><td><code>{d}</code></td><td>{p}</td></tr>' for m, s, t, d, p in PIPELINES)
    html = f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="robots" content="noindex" />
<title>站点产品说明 · 人读版 | Anaxagore</title>
<link rel="stylesheet" href="../../site.css" />
<style>{css}.prd-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,17rem),1fr));gap:1rem;margin:1rem 0}}.prd-card{{padding:1rem 1.1rem;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface)}}.prd-card h3{{margin:0 0 .4rem;font-size:1.02rem}}.prd-card p{{margin:0;color:var(--ink-soft);font-size:.92rem;line-height:1.6}}.pipe{{width:100%;border-collapse:collapse;font-size:.88rem}}.pipe th,.pipe td{{padding:.5rem .55rem;border-top:1px solid var(--line-soft);vertical-align:top;text-align:left;line-height:1.55}}.pipe th{{color:var(--muted);font-size:.75rem;font-family:var(--mono)}}.pipe code{{font-size:.82em}}.rule{{margin:.4rem 0;line-height:1.7}}.lead-p{{color:var(--ink-soft);line-height:1.8}}</style>
</head>
<body>
<!-- build:header -->
<!-- /build:header -->
<main class="wrap">
<p class="kicker">PRD</p>
<h1>站点产品说明（人读版）</h1>
<p class="lead-p">这一页是给人快速看懂整个站的：三张图、一张管线表、每个模块一段话。细节、规则、待办在各模块的文档里（GitHub 上渲染）；给 agent 用的压缩版在 <a href="{GH}agent.md" rel="noopener">agent.md</a>，仓库根目录的 <code>CLAUDE.md</code> 会让每次会话先读它。</p>

<h2>一、全站怎么跑</h2>
{c.arch_svg(SITE_DIAGRAM, SITE_MODULES)}
<ul>
<li class="rule"><b>没有服务器。</b>GitHub Actions 是后台，仓库里的 JSON 是数据库，<code>tools/build.py</code> 把 JSON 预渲染成 HTML，GitHub Pages 直接托管仓库根目录。</li>
<li class="rule"><b>AI 可插拔。</b>所有模型调用走 <code>tools/radar.py</code> 的 <code>call_llm_json</code>：有 Anthropic key 用 Claude，否则 Gemini；瞬时错误先重试再降级；都没有就退回关键词规则，页面上会标出来。</li>
<li class="rule"><b>任何一步失败都不能拖垮整轮。</b>源失败沿用上次结果并标 stale，状态页能看到。</li>
</ul>

<h2>二、模块地图</h2>
{c.arch_svg(MAP_DIAGRAM, MAP_MODULES)}
<div class="prd-grid">{cards}</div>

<h2>三、每天什么时候跑</h2>
{timeline_svg()}

<h2>四、每条管线的四个位置</h2>
<p class="lead-p">改任何模块，先找到它的这四个文件：源配置 → 脚本 → 数据文件 → 页面。</p>
<div class="table-wrap"><table class="pipe"><thead><tr><th>模块</th><th>源 / 配置</th><th>脚本</th><th>数据</th><th>页面</th></tr></thead><tbody>{rows}</tbody></table></div>

<h2>五、开源贡献路线的并行结构</h2>
{c.arch_svg(CONTRIB_DIAGRAM, CONTRIB_MODULES)}

<h2>六、全站共同约束</h2>
<ul>
<li class="rule">纯静态、无框架、无构建依赖；页面不加载第三方脚本（GoatCounter 统计和 giscus 评论除外）。</li>
<li class="rule">手机优先：340 / 360 / 390 / 430px 宽度下页面不能横向溢出，用 Playwright 量 <code>scrollWidth</code> 验证，桌面 Chrome 窄窗口截图不可信。</li>
<li class="rule"><code>radar/data/*.json</code> 是公开 API：不放密钥、不放私密内容；私密的在 <code>radar-inbox</code> 私有仓库。</li>
<li class="rule">功能改动走分支 + PR squash 合并到 master；机器人直接推 master，被拒时保留数据文件、回到最新 master 重渲染，不 rebase 生成物。</li>
<li class="rule">推荐位只说「推荐」，不写「推广」或免责声明；亲测的写清楚，没亲测的标出来。</li>
</ul>
<p class="radar-stats">本页由 <code>tools/prd_index.py</code> 生成；改图或文字请改脚本后重新生成。</p>
</main>
<footer class="site-footer"><div class="wrap"><span>© 2026 <!-- build:site-name --><!-- /build:site-name --></span><span><a href="../../about/">关于</a></span></div></footer>
<script src="../../site.js" defer></script>
</body>
</html>
'''
    out = ROOT / 'docs/prd/index.html'
    out.write_text(html, encoding='utf-8')
    print(f'写入 {out.relative_to(ROOT)}（{len(html)} 字）')

if __name__ == '__main__':
    main()
