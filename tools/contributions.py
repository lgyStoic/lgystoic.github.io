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
    'skill_fit':{'type':'string'},'engagement':{'type':'string'},'claim_comment':{'type':'string'},'pr_scope':{'type':'string'},'time_estimate':{'type':'string'},
},'required':['title','source_url','source_number','source_title','priority','compute','difficulty','why_core','goal','first_action','implementation_steps','likely_paths','validation','questions','risks','skill_fit','engagement','claim_comment','pr_scope','time_estimate']}
REPO_SCHEMA = {'type':'object','properties':{
    'repo':{'type':'string'},'fit':{'type':'string'},'current_direction':{'type':'string'},
    'recommended_order':{'type':'array','items':{'type':'string'}},'maintainer_path':{'type':'array','items':{'type':'string'}},
    'how_to_engage':{'type':'array','items':{'type':'string'}},'tasks':{'type':'array','items':TASK},
},'required':['repo','fit','current_direction','recommended_order','maintainer_path','how_to_engage','tasks']}


def api(path):
    headers={'Accept':'application/vnd.github+json','User-Agent':'contribution-radar/2.0'}
    token=os.environ.get('GITHUB_TOKEN','').strip()
    if token: headers['Authorization']='Bearer '+token
    with urllib.request.urlopen(urllib.request.Request('https://api.github.com/'+path.lstrip('/'),headers=headers),timeout=30) as response:
        return json.load(response)


def linked_prs(name, number):
    """Issue 时间线里被 PR 交叉引用 → 已有人在做。"""
    try:
        events = api(f'repos/{name}/issues/{number}/timeline?per_page=100')
    except Exception:
        return []
    prs = []
    for e in events:
        src = (e.get('source') or {}).get('issue') or {}
        if e.get('event') == 'cross-referenced' and src.get('pull_request'):
            prs.append({'number': src.get('number'), 'title': src.get('title', ''), 'url': src.get('html_url', ''), 'state': src.get('state', '')})
    return prs


def community_links(readme):
    links = []
    for m in re.finditer(r'https?://[^\s)\]"\'<>]+', readme or ''):
        u = m.group(0).rstrip('.,;')
        if re.search(r'slack|discord|discuss|forum|zulip|gitter|matrix|dev-mail|mailing|groups\.google|lark|feishu|dingtalk|wechat|qq', u, re.I) and u not in links:
            links.append(u)
    return links[:6]


def collect_repo(name):
    meta=api(f'repos/{name}')
    try:
        readme=api(f'repos/{name}/readme'); text=base64.b64decode(readme.get('content','')).decode('utf-8','replace')[:10000]
    except Exception: text=''
    contributing=''
    for path in ('CONTRIBUTING.md', 'docs/CONTRIBUTING.md', '.github/CONTRIBUTING.md', 'docs/developer_guide.md'):
        try:
            c=api(f'repos/{name}/contents/{path}'); contributing=base64.b64decode(c.get('content','')).decode('utf-8','replace')[:5000]; break
        except Exception: continue
    q=urllib.parse.quote(f'repo:{name} is:issue is:open')
    issues=api(f'search/issues?q={q}&sort=updated&order=desc&per_page=30').get('items',[])
    # 大仓库再补一轮标了 good first issue / help wanted 的
    q2=urllib.parse.quote(f'repo:{name} is:issue is:open label:"good first issue","help wanted"')
    try:
        extra=api(f'search/issues?q={q2}&sort=updated&order=desc&per_page=20').get('items',[])
    except Exception:
        extra=[]
    seen={i['number'] for i in issues}
    issues+= [i for i in extra if i['number'] not in seen]
    # 只对最近的 24 个 Issue 查时间线（认领 / 关联 PR），控制 API 次数
    linked={i['number']: linked_prs(name, i['number']) for i in issues[:24]}
    pulls=api(f'repos/{name}/pulls?state=open&sort=updated&direction=desc&per_page=10')
    releases=api(f'repos/{name}/releases?per_page=3'); commits=api(f'repos/{name}/commits?per_page=12')
    try: root=api(f'repos/{name}/contents')
    except Exception: root=[]
    return {'repo':name,'url':meta['html_url'],'description':meta.get('description'),'stars':meta.get('stargazers_count'),
        'forks':meta.get('forks_count'),'open_issues':meta.get('open_issues_count'),'pushed_at':meta.get('pushed_at'),
        'default_branch':meta.get('default_branch'),'readme':text,'contributing':contributing,'community':community_links(text),
        'root_paths':[x.get('path') for x in root if x.get('path')][:80],
        'issues':[{'number':i['number'],'title':i['title'],'body':(i.get('body') or '')[:3500],
                   'labels':[x['name'] for x in i.get('labels',[])],'comments':i.get('comments',0),
                   'assignees':[a.get('login') for a in (i.get('assignees') or [])],
                   'created_at':i.get('created_at'),'updated_at':i.get('updated_at'),'url':i['html_url'],
                   'linked_prs':linked.get(i['number'],[])} for i in issues],
        'pulls':[{'number':p['number'],'title':p['title'],'url':p['html_url']} for p in pulls],
        'releases':[{'name':r.get('name') or r.get('tag_name'),'date':r.get('published_at')} for r in releases],
        'commits':[{'message':c['commit']['message'].splitlines()[0],'date':c['commit']['author'].get('date'),'url':c.get('html_url')} for c in commits]}


def task_prompt(ev):
    compact={k:v for k,v in ev.items() if k not in ('stars','forks','open_issues')}
    return '''为下面这个开源仓库生成“可直接开工、并且知道怎么得体介入”的贡献任务卡。

候选人画像：资深 GPU kernel / 训练性能工程师。擅长 CUDA、Triton、CuTe/CUTLASS、PyTorch 内核与算子融合、分布式训练性能、扩散模型（DiT / 视频生成）推理加速、端侧部署（TensorRT、量化）。
算力：日常只有一台 MacBook；需要 GPU 时可以按小时租 4090 / A100，或用 Colab 免费 T4。所以「需要单卡 GPU 几小时」是可接受的，「需要多机多卡长时间训练」不可接受。

硬约束：
1. 每张卡必须绑定输入 issues 中一个真实、仍开放的 Issue；source_url、source_number、source_title 必须逐字取自输入，禁止虚构。
2. 介入是否得体是第一优先级：Issue 已有 assignees、或 linked_prs 里有 open 状态的 PR、或 pulls 里明显已覆盖 → 不要推荐去做，最多建议去 review / 补测试；在 engagement 字段写清楚判断依据。
3. 优先能发挥候选人 kernel / 性能专长、且维护者明显关心（评论多、最近更新、有 label）的任务。最多 6 张，宁缺毋滥；没有可靠任务返回空数组。
4. 实施步骤具体到调查、代码修改、测试与提交前沟通；likely_paths 只能依据 README、CONTRIBUTING、Issue 正文和根目录推断，不确定就写“需先定位”。
5. validation 写可执行的验收方式；questions 写开工前应在 Issue 询问维护者的问题。
6. claim_comment：一段英文、可直接贴到该 Issue 下的认领留言，礼貌、具体、不超过 120 词：说明理解、打算怎么做、需要维护者确认什么、大约多久出 PR。不要提候选人的个人经历。
7. pr_scope：一句话说明第一个 PR 该多小、边界在哪；time_estimate：诚实的工时估计，如「2–3 个晚上」。skill_fit：一句话说这张卡用到候选人哪项专长。
8. how_to_engage（仓库级）：3–5 条，基于 CONTRIBUTING 和 README：在哪讨论（community 链接）、PR 前要不要先开 Issue / RFC、CLA / DCO、测试和格式要求、维护者响应节奏。没有依据的不要写。
9. why_core 解释它如何通向长期维护职责，不写空泛鼓励。recommended_order 使用任务标题给出建议顺序。
10. 中文输出，代码、文件名、专有名词保留原文；claim_comment 用英文。

仓库证据：'''+json.dumps(compact,ensure_ascii=False)


def valid_tasks(generated,evidence):
    allowed={i['url']:i for i in evidence.get('issues',[])}; clean=[]
    for task in generated.get('tasks',[]):
        source=allowed.get(task.get('source_url'))
        if not source or task.get('source_number')!=source['number']: continue
        task['source_title']=source['title']
        task['issue_status']={'assignees':source.get('assignees',[]),'comments':source.get('comments',0),'labels':source.get('labels',[]),
                              'updated_at':source.get('updated_at'),'created_at':source.get('created_at'),
                              'open_prs':[p for p in source.get('linked_prs',[]) if p.get('state')=='open']}
        clean.append(task)
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


def status_badges(task):
    st=task.get('issue_status') or {}
    badges=[]
    if st.get('assignees'): badges.append(f'<span class="badge warn">已指派 {esc(", ".join(st["assignees"]))}</span>')
    if st.get('open_prs'): badges.append(f'<span class="badge warn">已有 PR #{esc(st["open_prs"][0].get("number"))}</span>')
    if not st.get('assignees') and not st.get('open_prs'): badges.append('<span class="badge ok">无人认领</span>')
    if st.get('comments') is not None: badges.append(f'<span class="badge">{st.get("comments",0)} 条评论</span>')
    for label in (st.get('labels') or [])[:3]: badges.append(f'<span class="badge">{esc(label)}</span>')
    if st.get('updated_at'): badges.append(f'<span class="badge">更新 {esc(st["updated_at"][:10])}</span>')
    return ''.join(badges)


def task_card(task,index):
    priority={'high':'优先','medium':'可选','low':'候补'}.get(str(task.get('priority','')).lower(),task.get('priority',''))
    claim=task.get('claim_comment','')
    return f'''<article class="task-card"><div class="task-top"><span class="task-index">任务 {index}</span><span>{esc(priority)} · {esc(task.get('difficulty'))} · {esc(task.get('compute'))} · {esc(task.get('time_estimate'))}</span></div>
<h2>{esc(task.get('title'))}</h2><p class="source-link"><a href="{esc(task.get('source_url'),True)}" rel="noopener noreferrer">Issue #{task.get('source_number')} · {esc(task.get('source_title'))} ↗</a></p>
<p class="badges">{status_badges(task)}</p>
<p><b>用到的专长：</b>{esc(task.get('skill_fit'))}</p><p><b>目标：</b>{esc(task.get('goal'))}</p><p><b>为什么值得长期做：</b>{esc(task.get('why_core'))}</p>
<div class="engage"><b>怎么介入：</b>{esc(task.get('engagement'))}<br><b>第一个 PR 的边界：</b>{esc(task.get('pr_scope'))}</div>
<div class="first-action"><b>第一步：</b>{esc(task.get('first_action'))}</div>
<details open><summary>认领留言（英文，可直接贴到 Issue）</summary><pre class="claim" data-claim>{esc(claim)}</pre><button type="button" class="btn-sm" data-copy-claim>复制留言</button></details>
<details><summary>大致实施方案</summary>{list_html(task.get('implementation_steps',[]))}</details><details><summary>可能涉及的目录或文件</summary>{list_html(task.get('likely_paths',[]))}</details>
<details><summary>验收方式</summary>{list_html(task.get('validation',[]))}</details><details><summary>开工前问题与风险</summary><h3>向维护者确认</h3>{list_html(task.get('questions',[]))}<h3>风险</h3>{list_html(task.get('risks',[]))}</details></article>'''


def detail_page(repo,updated,global_model):
    ev=repo.get('evidence',{}); tasks=repo.get('tasks',[])
    cards=''.join(task_card(t,i) for i,t in enumerate(tasks,1)) or '<p class="empty-state">当前开放 Issue 中没有足够可靠、适合你设备条件的任务。等待下次更新。</p>'
    stale=' · 本次生成失败，展示上次结果' if repo.get('stale') else ''
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(repo['repo'])} 贡献任务 | Anaxagore</title><meta name="description" content="{esc(repo['repo'])} 的具体开源贡献任务、Issue 链接与实施方案。"><link rel="canonical" href="https://lgystoic.github.io/radar/contributions/{slug(repo['repo'])}/"><link rel="stylesheet" href="../../../site.css"><style>.repo-hero{{padding-bottom:1.5rem;border-bottom:1px solid var(--line)}}.repo-meta,.task-top{{display:flex;gap:.7rem;flex-wrap:wrap;color:var(--muted)}}.task-card{{margin:1.2rem 0;padding:1.25rem;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface)}}.task-card h2{{margin:.45rem 0}}.task-card details{{margin-top:.8rem}}.task-index{{font-weight:700;color:var(--accent)}}.first-action{{margin:1rem 0;padding:.8rem 1rem;background:var(--bg-tint);border-radius:var(--radius)}}.source-link a{{font-weight:650}}.back-link{{display:inline-block;margin-bottom:1rem}}.badges{{display:flex;flex-wrap:wrap;gap:.4rem;margin:.5rem 0}}.badge{{padding:.1rem .55rem;border:1px solid var(--line);border-radius:999px;font-size:.75rem;color:var(--muted)}}.badge.ok{{border-color:#3a7d44;color:#3a7d44}}.badge.warn{{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}}.engage{{margin:.8rem 0;padding:.8rem 1rem;border-left:3px solid var(--accent);background:var(--bg-tint);border-radius:0 var(--radius) var(--radius) 0;line-height:1.7}}.claim{{white-space:pre-wrap;font-family:inherit;font-size:.92rem;line-height:1.6;margin:.5rem 0;padding:.8rem 1rem;background:var(--bg-tint);border-radius:var(--radius)}}</style></head><body><!-- build:header --><!-- /build:header --><main class="wrap"><a class="back-link" href="../">← 所有项目</a><section class="repo-hero"><p class="kicker">Contribution Tasks</p><h1>{esc(repo['repo'])}</h1><p>{esc(repo.get('fit'))}</p><p><b>当前方向：</b>{esc(repo.get('current_direction'))}</p><div class="repo-meta"><span>★ {ev.get('stars',0)}</span><span>Fork {ev.get('forks',0)}</span><span>{len(tasks)} 个候选任务</span><span>Gemini：{esc(repo.get('model') or global_model)}</span></div><p class="radar-stats">更新于 {esc(updated)}{stale} · <a href="{esc(ev.get('url','#'),True)}" rel="noopener noreferrer">打开仓库 ↗</a></p></section><section><h2>怎么介入这个项目</h2>{list_html(repo.get('how_to_engage',[]))}{('<p><b>社区入口：</b>'+' · '.join(f'<a href="{esc(u,True)}" rel="noopener noreferrer">{esc(u.split("//",1)[-1][:40])}</a>' for u in ev.get('community',[]))+'</p>') if ev.get('community') else ''}<h2>建议顺序</h2>{list_html(repo.get('recommended_order',[]))}<details><summary>成为长期维护者的路径</summary>{list_html(repo.get('maintainer_path',[]))}</details></section><section class="task-grid">{cards}</section></main><footer class="site-footer"><div class="wrap"><span>© 2026 Anaxagore</span><span><a href="../../../about/">关于</a></span></div></footer><script src="../../../site.js" defer></script><script>document.querySelectorAll('[data-copy-claim]').forEach(b=>b.addEventListener('click',()=>{{const t=b.parentElement.querySelector('[data-claim]').textContent;const done=()=>{{b.textContent='已复制';setTimeout(()=>b.textContent='复制留言',1500)}};if(navigator.clipboard)navigator.clipboard.writeText(t).then(done,done);else window.prompt('复制',t)}}))</script></body></html>'''


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
    parts=[f'<p class="radar-stats">更新于 {esc(d.get("updated"))} · 实际模型：{esc(d.get("model") or "未知")}</p>','<p class="lead-p">每个项目已经拆成独立页面。任务卡只绑定真实、仍开放的 GitHub Issue，标出是否已有人认领，并附一段可以直接贴的英文认领留言。</p>']
    picks=[]
    for r in d.get('repos',[]):
        for t in r.get('tasks',[]):
            st=t.get('issue_status') or {}
            if st.get('assignees') or st.get('open_prs'): continue
            pr={'high':0,'高':0,'medium':1,'中':1}.get(str(t.get('priority','')).lower(),2)
            hard={'easy':0,'low':0,'低':0,'简单':0,'medium':1,'中':1,'中等':1}.get(str(t.get('difficulty','')).lower(),2)
            kernel=any(k in (t.get('skill_fit','')+t.get('title','')).lower() for k in ('cuda','triton','kernel','算子','cutlass','cute','融合','性能'))
            picks.append((pr+hard-(1 if kernel else 0), -(st.get('comments') or 0), r['repo'], t))
    picks.sort(key=lambda x:(x[0],x[1]))
    if picks:
        parts.append('<section class="picks"><h2>本周先做这三个</h2><p class="radar-stats">无人认领、没有关联 PR、优先级高且能用上 kernel / 性能专长的任务排在前面。</p><ol class="pick-list">')
        for _,_,repo,t in picks[:3]:
            parts.append(f'<li><a href="./{slug(repo)}/">{esc(repo)}</a> · <a href="{esc(t.get("source_url"),True)}" rel="noopener noreferrer">#{t.get("source_number")}</a> {esc(t.get("title"))}<br><span class="radar-stats">{esc(t.get("difficulty"))} · {esc(t.get("compute"))} · {esc(t.get("time_estimate"))} · {esc(t.get("skill_fit"))}</span></li>')
        parts.append('</ol></section>')
    parts.append('<div class="contribution-grid">')
    for r in d.get('repos',[]):
        ev=r.get('evidence',{}); tasks=r.get('tasks',[]); preview=''.join(f'<li>{esc(t.get("title"))}</li>' for t in tasks[:3])
        parts.append(f'<article class="contribution-card"><p class="kicker">{len(tasks)} 个候选任务</p><h2><a href="./{slug(r["repo"])}/">{esc(r["repo"])}</a></h2><p>{esc(r.get("fit"))}</p><p class="radar-stats">★ {ev.get("stars",0)} · 最近推送 {(ev.get("pushed_at") or "未知")[:10]}</p><ul>{preview}</ul><p><a href="./{slug(r["repo"])}/">查看任务卡与实施方案 →</a></p></article>')
    parts.append('</div>'); return '\n'.join(parts)


if __name__=='__main__': main()
