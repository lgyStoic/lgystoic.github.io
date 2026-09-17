#!/usr/bin/env python3
"""GitHub signals -> Gemini task cards -> project-specific contribution pages."""
import base64, html, json, os, re, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
import radar

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / 'radar/contribution_repos.json'
DATA = ROOT / 'radar/data/contributions.json'
DETAIL_ROOT = ROOT / 'radar/contributions'

TASK = {'type':'object','properties':{
    'title':{'type':'string'},'source_url':{'type':'string'},'source_number':{'type':'integer'},'source_title':{'type':'string'},
    'priority':{'type':'string'},'compute':{'type':'string'},'difficulty':{'type':'string'},'why_core':{'type':'string'},
    'goal':{'type':'string'},'first_action':{'type':'string'},'implementation_steps':{'type':'array','items':{'type':'string'}},
    'likely_paths':{'type':'array','items':{'type':'string'}},'validation':{'type':'array','items':{'type':'string'}},
    'questions':{'type':'array','items':{'type':'string'}},'risks':{'type':'array','items':{'type':'string'}},
},'required':['title','source_url','source_number','source_title','priority','compute','difficulty','why_core','goal','first_action','implementation_steps','likely_paths','validation','questions','risks']}
REPO_SCHEMA = {'type':'object','properties':{
    'repo':{'type':'string'},'fit':{'type':'string'},'current_direction':{'type':'string'},
    'recommended_order':{'type':'array','items':{'type':'string'}},'maintainer_path':{'type':'array','items':{'type':'string'}},
    'tasks':{'type':'array','items':TASK},
},'required':['repo','fit','current_direction','recommended_order','maintainer_path','tasks']}


def api(path):
    headers={'Accept':'application/vnd.github+json','User-Agent':'contribution-radar/2.0'}
    token=os.environ.get('GITHUB_TOKEN','').strip()
    if token: headers['Authorization']='Bearer '+token
    with urllib.request.urlopen(urllib.request.Request('https://api.github.com/'+path.lstrip('/'),headers=headers),timeout=30) as response:
        return json.load(response)


def collect_repo(name):
    meta=api(f'repos/{name}')
    try:
        readme=api(f'repos/{name}/readme'); text=base64.b64decode(readme.get('content','')).decode('utf-8','replace')[:10000]
    except Exception: text=''
    q=urllib.parse.quote(f'repo:{name} is:issue is:open')
    issues=api(f'search/issues?q={q}&sort=updated&order=desc&per_page=30').get('items',[])
    pulls=api(f'repos/{name}/pulls?state=open&sort=updated&direction=desc&per_page=10')
    releases=api(f'repos/{name}/releases?per_page=3'); commits=api(f'repos/{name}/commits?per_page=12')
    try: root=api(f'repos/{name}/contents')
    except Exception: root=[]
    return {'repo':name,'url':meta['html_url'],'description':meta.get('description'),'stars':meta.get('stargazers_count'),
        'forks':meta.get('forks_count'),'open_issues':meta.get('open_issues_count'),'pushed_at':meta.get('pushed_at'),
        'default_branch':meta.get('default_branch'),'readme':text,'root_paths':[x.get('path') for x in root if x.get('path')][:80],
        'issues':[{'number':i['number'],'title':i['title'],'body':(i.get('body') or '')[:3500],
                   'labels':[x['name'] for x in i.get('labels',[])],'comments':i.get('comments',0),
                   'updated_at':i.get('updated_at'),'url':i['html_url']} for i in issues],
        'pulls':[{'number':p['number'],'title':p['title'],'url':p['html_url']} for p in pulls],
        'releases':[{'name':r.get('name') or r.get('tag_name'),'date':r.get('published_at')} for r in releases],
        'commits':[{'message':c['commit']['message'].splitlines()[0],'date':c['commit']['author'].get('date'),'url':c.get('html_url')} for c in commits]}


def task_prompt(ev):
    compact={k:v for k,v in ev.items() if k not in ('stars','forks','open_issues')}
    return '''为下面这个开源仓库生成“可直接开工”的贡献任务卡。候选人擅长 AI Infra、DiT、端侧部署、训练与推理加速，但目前没有高性能 GPU。

硬约束：
1. 每张卡必须绑定输入 issues 中一个真实、仍开放的 Issue；source_url、source_number、source_title 必须逐字取自输入，禁止虚构。
2. 不把开放 PR 当作待领取任务；pulls 仅用于判断是否已有实现，若 Issue 明显已被 PR 覆盖就不要推荐。
3. 优先无 GPU/低算力可验证且有维护价值的任务。最多 6 张，宁缺毋滥；没有可靠任务可以返回空数组。
4. 实施步骤必须具体到调查、代码修改、测试与提交前沟通；likely_paths 只能依据 README、Issue 正文和根目录推断，不确定时明确写“需先定位”，不要编造文件。
5. validation 写可执行的验收方式；questions 写开工前应在 Issue 询问维护者的问题。
6. why_core 解释它如何通向长期维护职责，不写空泛鼓励。recommended_order 使用任务标题给出建议顺序。
7. 中文输出，代码、文件名和专有名词保留原文。

仓库证据：'''+json.dumps(compact,ensure_ascii=False)


def valid_tasks(generated,evidence):
    allowed={i['url']:i for i in evidence.get('issues',[])}; clean=[]
    for task in generated.get('tasks',[]):
        source=allowed.get(task.get('source_url'))
        if not source or task.get('source_number')!=source['number']: continue
        task['source_title']=source['title']; clean.append(task)
    generated['tasks']=clean[:6]
    return generated


def main():
    names=json.loads(CONFIG.read_text()); previous=json.loads(DATA.read_text()) if DATA.exists() else {'repos':[]}
    old={x.get('repo'):x for x in previous.get('repos',[])}; repos=[]; failures=[]; models=[]
    for name in names:
        try:
            evidence=collect_repo(name)
            generated=radar.call_llm_json('你是资深开源维护者与 AI 系统工程师。把真实 GitHub Issue 变成严谨、可执行、可验证的贡献计划。',task_prompt(evidence),REPO_SCHEMA,label='contribution-'+name.replace('/','-'))
            if not generated: raise RuntimeError('GeminiGenerationFailed')
            generated['repo']=name; generated=valid_tasks(generated,evidence)
            generated['evidence']={k:v for k,v in evidence.items() if k!='readme'}
            generated['model']=radar.LAST_MODEL_USED; models.append(radar.LAST_MODEL_USED); repos.append(generated)
        except Exception as exc:
            failures.append({'repo':name,'error':type(exc).__name__})
            if name in old:
                stale=old[name]; stale['stale']=True; repos.append(stale)
    model=models[0] if models and len(set(models))==1 else ' / '.join(dict.fromkeys(models))
    out={'updated':datetime.now(timezone.utc).isoformat(timespec='seconds'),'model':model,'repos':repos,'failures':failures}
    DATA.parent.mkdir(parents=True,exist_ok=True); DATA.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(f'贡献任务：{len(repos)} 个仓库，{sum(len(x.get("tasks",[])) for x in repos)} 张卡片；失败 {len(failures)}；模型 {model}')


def esc(value,quote=False): return html.escape(str(value or ''),quote=quote)
def slug(repo): return re.sub(r'[^a-z0-9._-]+','-',repo.lower().replace('/','--')).strip('-')
def list_html(items): return '<ul>'+''.join(f'<li>{esc(x)}</li>' for x in items)+'</ul>'


def task_card(task,index):
    priority={'high':'优先','medium':'可选','low':'候补'}.get(task.get('priority'),task.get('priority',''))
    return f'''<article class="task-card"><div class="task-top"><span class="task-index">任务 {index}</span><span>{esc(priority)} · {esc(task.get('difficulty'))} · {esc(task.get('compute'))}</span></div>
<h2>{esc(task.get('title'))}</h2><p class="source-link"><a href="{esc(task.get('source_url'),True)}" rel="noopener noreferrer">Issue #{task.get('source_number')} · {esc(task.get('source_title'))} ↗</a></p>
<p><b>目标：</b>{esc(task.get('goal'))}</p><p><b>为什么值得长期做：</b>{esc(task.get('why_core'))}</p><div class="first-action"><b>第一步：</b>{esc(task.get('first_action'))}</div>
<details open><summary>大致实施方案</summary>{list_html(task.get('implementation_steps',[]))}</details><details><summary>可能涉及的目录或文件</summary>{list_html(task.get('likely_paths',[]))}</details>
<details><summary>验收方式</summary>{list_html(task.get('validation',[]))}</details><details><summary>开工前问题与风险</summary><h3>向维护者确认</h3>{list_html(task.get('questions',[]))}<h3>风险</h3>{list_html(task.get('risks',[]))}</details></article>'''


def detail_page(repo,updated,global_model):
    ev=repo.get('evidence',{}); tasks=repo.get('tasks',[])
    cards=''.join(task_card(t,i) for i,t in enumerate(tasks,1)) or '<p class="empty-state">当前开放 Issue 中没有足够可靠、适合你设备条件的任务。等待下次更新。</p>'
    stale=' · 本次生成失败，展示上次结果' if repo.get('stale') else ''
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(repo['repo'])} 贡献任务 | Anaxagore</title><meta name="description" content="{esc(repo['repo'])} 的具体开源贡献任务、Issue 链接与实施方案。"><link rel="canonical" href="https://lgystoic.github.io/radar/contributions/{slug(repo['repo'])}/"><link rel="stylesheet" href="../../../site.css"><style>.repo-hero{{padding-bottom:1.5rem;border-bottom:1px solid var(--line)}}.repo-meta,.task-top{{display:flex;gap:.7rem;flex-wrap:wrap;color:var(--muted)}}.task-card{{margin:1.2rem 0;padding:1.25rem;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface)}}.task-card h2{{margin:.45rem 0}}.task-card details{{margin-top:.8rem}}.task-index{{font-weight:700;color:var(--accent)}}.first-action{{margin:1rem 0;padding:.8rem 1rem;background:var(--bg-tint);border-radius:var(--radius)}}.source-link a{{font-weight:650}}.back-link{{display:inline-block;margin-bottom:1rem}}</style></head><body><!-- build:header --><!-- /build:header --><main class="wrap"><a class="back-link" href="../">← 所有项目</a><section class="repo-hero"><p class="kicker">Contribution Tasks</p><h1>{esc(repo['repo'])}</h1><p>{esc(repo.get('fit'))}</p><p><b>当前方向：</b>{esc(repo.get('current_direction'))}</p><div class="repo-meta"><span>★ {ev.get('stars',0)}</span><span>Fork {ev.get('forks',0)}</span><span>{len(tasks)} 个候选任务</span><span>Gemini：{esc(repo.get('model') or global_model)}</span></div><p class="radar-stats">更新于 {esc(updated)}{stale} · <a href="{esc(ev.get('url','#'),True)}" rel="noopener noreferrer">打开仓库 ↗</a></p></section><section><h2>建议顺序</h2>{list_html(repo.get('recommended_order',[]))}<details><summary>成为长期维护者的路径</summary>{list_html(repo.get('maintainer_path',[]))}</details></section><section class="task-grid">{cards}</section></main><footer class="site-footer"><div class="wrap"><span>© 2026 Anaxagore</span><span><a href="../../../about/">关于</a></span></div></footer><script src="../../../site.js" defer></script></body></html>'''


def write_detail_pages(data):
    valid=set()
    for repo in data.get('repos',[]):
        name=slug(repo['repo']); valid.add(name); folder=DETAIL_ROOT/name; folder.mkdir(parents=True,exist_ok=True)
        (folder/'index.html').write_text(detail_page(repo,data.get('updated',''),data.get('model','')),encoding='utf-8')
    for page in DETAIL_ROOT.glob('*/index.html'):
        if page.parent.name not in valid:
            page.unlink()
            try: page.parent.rmdir()
            except OSError: pass


def render():
    if not DATA.exists(): return '<p>路线图尚未生成。</p>'
    d=json.loads(DATA.read_text()); write_detail_pages(d)
    parts=[f'<p class="radar-stats">更新于 {esc(d.get("updated"))} · 实际模型：{esc(d.get("model") or "未知")}</p>','<p class="lead-p">每个项目已经拆成独立页面。任务卡只绑定真实、仍开放的 GitHub Issue，并给出实施与验收方案。</p>','<div class="contribution-grid">']
    for r in d.get('repos',[]):
        ev=r.get('evidence',{}); tasks=r.get('tasks',[]); preview=''.join(f'<li>{esc(t.get("title"))}</li>' for t in tasks[:3])
        parts.append(f'<article class="contribution-card"><p class="kicker">{len(tasks)} 个候选任务</p><h2><a href="./{slug(r["repo"])}/">{esc(r["repo"])}</a></h2><p>{esc(r.get("fit"))}</p><p class="radar-stats">★ {ev.get("stars",0)} · 最近推送 {(ev.get("pushed_at") or "未知")[:10]}</p><ul>{preview}</ul><p><a href="./{slug(r["repo"])}/">查看任务卡与实施方案 →</a></p></article>')
    parts.append('</div>'); return '\n'.join(parts)


if __name__=='__main__': main()
