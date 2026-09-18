#!/usr/bin/env python3
"""GitHub signals -> Gemini task cards -> project-specific contribution pages."""
import base64, html, json, os, re, urllib.error, urllib.parse, urllib.request
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
    'compute_class':{'type':'string'},'kind':{'type':'string'},'local_repro':{'type':'string'},
},'required':['title','source_url','source_number','source_title','priority','compute','difficulty','why_core','goal','first_action','implementation_steps','likely_paths','validation','questions','risks','skill_fit','engagement','claim_comment','pr_scope','time_estimate','compute_class','kind','local_repro']}
TOPUP_SCHEMA = {'type':'object','properties':{'tasks':{'type':'array','items':TASK}},'required':['tasks']}
def _arr(): return {'type':'array','items':{'type':'string'}}
def _objs(*fields): return {'type':'array','items':{'type':'object','properties':{f:{'type':'string'} for f in fields},'required':list(fields)}}

CHAPTERS = [
    ('positioning', '项目定位', {'type':'object','properties':{
        'overview':{'type':'string'},'problem':{'type':'string'},'users':{'type':'string'},'landscape':_objs('project','difference'),
        'stage':{'type':'string'},'capabilities':_objs('capability','where','maturity'),'stack':_arr(),'numbers':{'type':'string'},
    },'required':['overview','problem','users','landscape','stage','capabilities','stack','numbers']}),
    ('codemap', '架构与代码地图', {'type':'object','properties':{
        'layers':{'type':'string'},'modules':_objs('module','path','role','entry_points','depends_on','size','notes'),
        'data_flow':{'type':'string'},'key_types':_objs('name','path','purpose'),'extension_points':_objs('where','how'),
        'hotspots':_objs('path','why'),'reading_order':_arr(),
        'diagram':{'type':'object','properties':{'layers':_objs('name','modules'),'edges':_objs('from','to','label'),'caption':{'type':'string'}},'required':['layers','edges','caption']},
        'flow':_objs('step','component','path'),
    },'required':['layers','modules','data_flow','key_types','extension_points','hotspots','reading_order','diagram','flow']}),
    ('runbook', '本地跑起来', {'type':'object','properties':{
        'install':_arr(),'no_gpu_paths':{'type':'string'},'smoke_test':_arr(),'test_suite':{'type':'string'},'debug_tips':_arr(),
        'ci':{'type':'string'},'pitfalls':_arr(),
    },'required':['install','no_gpu_paths','smoke_test','test_suite','debug_tips','ci','pitfalls']}),
    ('community', '维护者与社区', {'type':'object','properties':{
        'cadence':{'type':'string'},'people':_objs('who','role','evidence'),'process':{'type':'string'},'review_style':{'type':'string'},
        'channels':_arr(),'etiquette':_arr(),'what_they_want':_arr(),
    },'required':['cadence','people','process','review_style','channels','etiquette','what_they_want']}),
    ('entry', '切入方案', {'type':'object','properties':{
        'gaps':_objs('gap','evidence','why_you'),'ownership_target':{'type':'string'},'why_this_target':{'type':'string'},
        'phase_30':_arr(),'phase_60':_arr(),'phase_90':_arr(),'first_prs':_objs('title','scope','why_safe'),
        'signals_of_progress':_arr(),'risks':_objs('risk','mitigation'),
    },'required':['gaps','ownership_target','why_this_target','phase_30','phase_60','phase_90','first_prs','signals_of_progress','risks']}),
]
CHAPTER_BRIEF = {
    'positioning': """- overview：400–600 字，这个项目是什么、为什么存在、和同类的关系、现在什么阶段。
- problem / users：解决的具体问题、目标用户和典型使用场景。
- landscape：3–6 个同类项目及差别（只写你有把握的）。
- capabilities：6–12 条核心能力，where 指出对应目录或文件，maturity 写成熟 / 实验 / 缺失。
- stack：语言、框架、底层依赖、构建、CI。numbers：从证据里能读出的规模数字（star、目录文件数、提交频率、Release）。
- maturity 以 README 自己的说法为准：README 标 Experimental / Early / WIP 的后端或能力，就写「实验」，不要拔高成「原生支持」。""",
    'codemap': """- layers：分层描述（入口层 / 调度层 / 执行层 / kernel 层 / 工具层之类），300 字以上。
- modules：8–16 条，每条 module、path（必须来自目录树或代码路径）、role、entry_points（关键类 / 函数 / 文件，来自源码片段或路径名，不确定写「需验证」）、depends_on、size（文件数量级）、notes。
- data_flow：400 字以上，一次请求 / 推理 / 训练从入口到输出的完整路径，关键数据结构与调度点。
- key_types：8–15 个关键类型或函数，写路径和用途。
- extension_points：新模型 / 新后端 / 新 kernel / 新调度策略分别在哪接、怎么接。
- hotspots：结合提交热点 5–8 条。reading_order：建议阅读顺序，10 步以内，每步一个文件或目录。
- diagram：架构图的结构化数据，页面会据此画图。layers 自上而下 3–6 层（如 接入层 / 调度层 / 执行层 / 硬件层），每层的 modules 用逗号分隔列出属于它的模块名，必须与 modules 里的 module 一字不差，每个模块只出现在一层；edges 8–16 条模块间的调用或数据依赖，from / to 用模块名，label 2–6 个字写传的是什么（请求 / Tensor / 配置…），只写有证据的；caption 一句话说明这张图。
- flow：一次典型请求的 5–9 步，与 data_flow 一致：step 是动作（8 字内），component 是模块名或类名，path 是文件路径（不确定写「需验证」）。""",
    'runbook': """- install：在没有 GPU 的 MacBook（Apple Silicon）上安装的具体命令序列，依据 README / pyproject / CMakeLists；哪些依赖要跳过或替换。
- no_gpu_paths：哪些代码路径能在 CPU / MPS / Metal 上真正执行，哪些只能读代码或用 Colab T4 验证。
- smoke_test：3–6 条最小可运行示例命令，只写真正会跑推理 / 测试的命令；文档站、Lint 脚本不算冒烟测试。test_suite：测试框架、目录、怎么只跑 CPU 子集、大概耗时。
- debug_tips：断点、日志开关、环境变量、profiling 入口。ci：CI 用什么、跑哪些、PR 会被什么卡住。pitfalls：常见坑。""",
    'community': """- cadence：提交与 Release 频率（用 commits / releases 证据）。people：主要维护者 3–8 人，role 和 evidence（从提交作者、Issue 指派推断）。
- process：贡献流程（先 Issue / RFC？CLA / DCO？pre-commit？）。review_style：从 Issue / PR 评论推断的 Review 风格与响应速度。
- channels：只填证据（README / CONTRIBUTING / community）里出现过的链接，原文照抄；不要猜 Slack / Discord 的频道名。etiquette：这个社区里得体与不得体的做法。what_they_want：维护者当前最想要的帮助（从 roadmap / help wanted / 评论推断）。""",
    'entry': """- gaps：6–10 条，这个项目当前缺的、且候选人在无 GPU 条件下能补的，每条给 evidence 和 why_you。
- ownership_target / why_this_target：建议长期负责的模块或方向，为什么既够核心又能无 GPU 起步，通向维护者身份的路径。
- phase_30 / 60 / 90：每阶段 5–8 条具体可勾选动作（读哪些文件、跑什么、提什么类型 PR、在哪露面、何时申请 triage / reviewer）。
- first_prs：3–5 个第一批 PR 的题目、范围和为什么安全。不要假设未证实的 bug（例如「修复潜在的资源泄漏」）：要么绑定一个真实 Issue，要么是补测试 / 文档 / 基准脚本 / 后端对照这类不依赖假设的工作。signals_of_progress：怎么判断自己在这个项目里站住了。risks：风险与对策各 4–8 条。""",
}
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


def repo_options(entry):
    """列表项可以是 "owner/repo" 或 {"repo": ..., "focus": bool, "young": bool}。"""
    if isinstance(entry, str):
        return {'repo': entry, 'focus': False, 'young': False}
    return {'repo': entry['repo'], 'focus': bool(entry.get('focus')), 'young': bool(entry.get('young'))}


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


def repo_tree(name, branch):
    """递归目录树（上限 2000 条），汇总成「顶层目录 → 子目录/文件数」，给模型看架构。"""
    try:
        tree=api(f'repos/{name}/git/trees/{branch}?recursive=1').get('tree',[])
    except Exception:
        return {}, []
    summary={}
    for node in tree[:6000]:
        parts=node.get('path','').split('/')
        top=parts[0]
        entry=summary.setdefault(top,{'files':0,'dirs':set()})
        if node.get('type')=='blob': entry['files']+=1
        if len(parts)>=2: entry['dirs'].add(parts[1])
    compact={k:{'files':v['files'],'children':sorted(v['dirs'])[:40]} for k,v in summary.items()}
    code_paths=[n['path'] for n in tree if n.get('type')=='blob' and re.search(r'\.(py|cu|cuh|cc|cpp|h|hpp|rs|ts|mm|metal)$',n.get('path',''))]
    return compact, code_paths[:400]


def key_files(name):
    out={}
    for path in ('pyproject.toml','setup.py','CMakeLists.txt','Cargo.toml','package.json','docs/index.md','docs/README.md','ARCHITECTURE.md','docs/architecture.md','AGENTS.md','CLAUDE.md'):
        try:
            c=api(f'repos/{name}/contents/{path}')
            if c.get('encoding')=='base64':
                out[path]=base64.b64decode(c.get('content','')).decode('utf-8','replace')[:3000]
        except Exception:
            continue
    return out


def commit_hotspots(name, commits, limit=15):
    """最近 N 个提交改了哪些文件，按前两级路径计数 → 活跃热点。"""
    counts={}
    for c in commits[:limit]:
        sha=(c.get('url') or '').rsplit('/',1)[-1]
        if not sha: continue
        try:
            detail=api(f'repos/{name}/commits/{sha}')
        except Exception:
            continue
        for f in detail.get('files',[])[:60]:
            key='/'.join(f.get('filename','').split('/')[:2])
            counts[key]=counts.get(key,0)+1
    return sorted(counts.items(), key=lambda x:-x[1])[:20]


def source_snippets(name, code_paths, hotspots, limit=10, chars=3500):
    """挑关键源码文件的开头（入口 / 调度 / 引擎 / kernel 相关，优先落在热点目录），让模型写出真实的类名和入口。"""
    hot_dirs=[h[0] for h in hotspots[:8]]
    def score(path):
        base=path.rsplit('/',1)[-1].lower()
        sc=0
        if any(path.startswith(h) for h in hot_dirs): sc+=3
        if re.search(r'(__init__|__main__|main|server|engine|scheduler|runtime|executor|pipeline|model_runner|kernel|attention|launch|entrypoint|api|cli)', base): sc+=2
        if base in ('__init__.py',) and path.count('/')>2: sc-=2
        sc-=path.count('/')*0.2
        return -sc
    picked=[]
    for path in sorted(code_paths, key=score):
        if len(picked)>=limit: break
        if re.search(r'(test|bench|example|docs?/|third_party|vendor)', path): continue
        picked.append(path)
    out={}
    for path in picked:
        try:
            c=api(f'repos/{name}/contents/{urllib.parse.quote(path)}')
            if c.get('encoding')=='base64':
                out[path]=base64.b64decode(c.get('content','')).decode('utf-8','replace')[:chars]
        except Exception:
            continue
    return out


def collect_repo(name, opts=None):
    opts=opts or {}
    meta=api(f'repos/{name}')
    try:
        readme=api(f'repos/{name}/readme'); text=base64.b64decode(readme.get('content','')).decode('utf-8','replace')[:20000 if (opts or {}).get('focus') else 12000]
    except Exception: text=''
    contributing=''
    for path in ('CONTRIBUTING.md', 'docs/CONTRIBUTING.md', '.github/CONTRIBUTING.md', 'docs/developer_guide.md'):
        try:
            c=api(f'repos/{name}/contents/{path}'); contributing=base64.b64decode(c.get('content','')).decode('utf-8','replace')[:5000]; break
        except Exception: continue
    q=urllib.parse.quote(f'repo:{name} is:issue is:open')
    issues=api(f'search/issues?q={q}&sort=updated&order=desc&per_page={100 if opts.get("focus") else 30}').get('items',[])
    # 大仓库再补一轮标了 good first issue / help wanted 的
    q2=urllib.parse.quote(f'repo:{name} is:issue is:open label:"good first issue","help wanted"')
    try:
        extra=api(f'search/issues?q={q2}&sort=updated&order=desc&per_page=20').get('items',[])
    except Exception:
        extra=[]
    seen={i['number'] for i in issues}
    issues+= [i for i in extra if i['number'] not in seen]
    if opts.get('focus'):
        # 重点仓库：再按候选人方向定向搜索，扩大候选池
        for kw in ('Apple OR MLX OR Metal OR CPU', 'perf OR performance OR latency OR throughput', 'scheduler OR batching OR runtime',
                   'kernel OR "CUDA graph" OR triton OR fused', 'profiling OR benchmark OR telemetry', 'test OR CI OR flaky', 'roadmap OR tracking OR RFC'):
            qk=urllib.parse.quote(f'repo:{name} is:issue is:open {kw}')
            try:
                hits=api(f'search/issues?q={qk}&sort=comments&order=desc&per_page=20').get('items',[])
            except Exception:
                hits=[]
            seen={i['number'] for i in issues}
            issues+= [i for i in hits if i['number'] not in seen]
    # 查时间线（认领 / 关联 PR）：重点仓库 120 个，其余 40 个；没查到的 Issue 不进优先候选池
    linked={i['number']: linked_prs(name, i['number']) for i in issues[:120 if opts.get('focus') else 40]}
    pulls=api(f'repos/{name}/pulls?state=open&sort=updated&direction=desc&per_page=10')
    releases=api(f'repos/{name}/releases?per_page=3'); commits=api(f'repos/{name}/commits?per_page=12')
    try: root=api(f'repos/{name}/contents')
    except Exception: root=[]
    tree_summary, code_paths = repo_tree(name, meta.get('default_branch') or 'main')
    hotspots=commit_hotspots(name, commits)
    files=key_files(name)
    snippets=source_snippets(name, code_paths, hotspots)
    young=bool(opts.get('young')) or (meta.get('open_issues_count') or 0) < 5
    return {'repo':name,'url':meta['html_url'],'description':meta.get('description'),'stars':meta.get('stargazers_count'),
        'focus':bool(opts.get('focus')),'young':young,
        'tree':tree_summary,'code_paths':code_paths,'commit_hotspots':hotspots,'key_files':files,'source_snippets':snippets,
        'forks':meta.get('forks_count'),'open_issues':meta.get('open_issues_count'),'pushed_at':meta.get('pushed_at'),
        'default_branch':meta.get('default_branch'),'readme':text,'contributing':contributing,'community':community_links(text),
        'root_paths':[x.get('path') for x in root if x.get('path')][:80],
        'issues':[{'number':i['number'],'title':i['title'],'body':(i.get('body') or '')[:3500],
                   'labels':[x['name'] for x in i.get('labels',[])],'comments':i.get('comments',0),
                   'assignees':[a.get('login') for a in (i.get('assignees') or [])],
                   'created_at':i.get('created_at'),'updated_at':i.get('updated_at'),'url':i['html_url'],
                   'linked_prs':linked.get(i['number'],[]),'prs_checked':i['number'] in linked} for i in issues],
        'pulls':[{'number':p['number'],'title':p['title'],'url':p['html_url']} for p in pulls],
        'releases':[{'name':r.get('name') or r.get('tag_name'),'date':r.get('published_at')} for r in releases],
        'commits':[{'message':c['commit']['message'].splitlines()[0],'date':c['commit']['author'].get('date'),'url':c.get('html_url')} for c in commits]}


PROFILE = """候选人画像：资深 GPU kernel / 训练性能工程师。擅长 CUDA、Triton、CuTe/CUTLASS、PyTorch 内核与算子融合、分布式训练性能、扩散模型（DiT / 视频生成）推理加速、端侧部署（TensorRT、量化）。
算力（硬约束）：目前没有任何 GPU，只有一台 MacBook Air（Apple Silicon，16GB）。开发与验证必须在 CPU / Apple Silicon 上完成，最多用 Colab 免费 T4 做几十分钟的最终确认。"""


def chapter_prompt(ev, key, title, brief, done):
    compact={k:v for k,v in ev.items() if k not in ('issues','pulls','stars','forks','open_issues')}
    if key in ('positioning','community'):
        compact={k:v for k,v in compact.items() if k not in ('source_snippets','code_paths')}
    if key=='community':
        compact['issues']=[{k:i.get(k) for k in ('number','title','labels','comments','assignees','updated_at')} for i in ev.get('issues',[])[:40]]
        compact['pulls']=ev.get('pulls',[])
    prior=''
    if done:
        prior='\n\n前面章节已经写好的结论（保持一致，不要重复，可以引用）：'+json.dumps({k:_shrink(v) for k,v in done.items()},ensure_ascii=False)
    return PROFILE+prior+f'''

请为下面这个开源仓库写「{title}」这一章，读者是上面这位候选人，目的是先彻底看懂这个库，再决定怎么切入。要求详细、具体、每个判断都能对应到证据（README、关键文件、目录树、代码路径、源码片段、最近提交与提交热点、CONTRIBUTING、Issue）。不确定的写「需验证」，绝不编造不存在的文件或类。

本章字段要求：
{brief}

全部中文，代码、文件名、类名、专有名词保留原文。

仓库证据：'''+json.dumps(compact,ensure_ascii=False)


def _shrink(v, n=1200):
    text=json.dumps(v,ensure_ascii=False)
    return json.loads(text) if len(text)<=n else text[:n]+'…'


def run_analysis(ev, label):
    """逐章生成，后一章能看到前面章节的结论。任一章失败则整体失败。"""
    done={}; models={}
    for key, title, schema in CHAPTERS:
        out=radar.call_llm_json('你是资深开源维护者与 AI 系统架构师，擅长读懂陌生仓库并规划切入路径。只依据证据，不编造。',
                                chapter_prompt(ev, key, title, CHAPTER_BRIEF[key], done), schema, label=f'{label}-{key}')
        if not out: raise RuntimeError(f'GeminiChapterFailed:{key}')
        done[key]=out; models[key]=radar.LAST_MODEL_USED
    return done, models


def summarize_models(models):
    """把每阶段实际用到的模型压成一句：全一致就一个名字，否则点名哪些阶段降级了。"""
    names=[m for m in models.values() if m]
    if not names: return ''
    main=max(set(names), key=names.count)
    downgraded=[k for k,m in models.items() if m and m!=main]
    if not downgraded: return main
    return main+'（'+'、'.join(f'{STAGE_NAMES.get(k,k)}：{models[k]}' for k in downgraded)+'）'


STAGE_NAMES={'positioning':'第一章','codemap':'第二章','runbook':'第三章','community':'第四章','entry':'第五章','tasks':'任务卡','tasks-topup':'补卡'}


def is_claimed(issue):
    """已有人认领：有 assignee，或时间线里挂着 open 状态的 PR。"""
    return bool(issue.get('assignees')) or any(p.get('state')=='open' for p in issue.get('linked_prs') or [])


def candidate_pool(ev):
    """优先候选池：无人认领、查过时间线且没有 open PR 的 Issue，按更新时间新→旧。"""
    pool=[i for i in ev.get('issues',[]) if not is_claimed(i) and i.get('prs_checked', True)]
    return sorted(pool, key=lambda i: str(i.get('updated_at') or ''), reverse=True)


def _issue_line(i):
    tail=f"，PR {'、'.join('#'+str(p.get('number')) for p in i.get('linked_prs',[]) if p.get('state')=='open')}" if any(p.get('state')=='open' for p in i.get('linked_prs',[])) else ''
    who=f"，指派 {'、'.join(i['assignees'])}" if i.get('assignees') else ''
    labels=f"，标签 {'/'.join(i.get('labels') or [])}" if i.get('labels') else ''
    return f"- #{i['number']} {i['title']}（{i.get('comments',0)} 条评论，更新 {str(i.get('updated_at') or '')[:10]}{labels}{who}{tail}）"


def task_prompt(ev, analysis=None, existing=None, need=0):
    pool=candidate_pool(ev); pool_numbers={i['number'] for i in pool}
    claimed=[i for i in ev.get('issues',[]) if is_claimed(i)]
    compact={k:v for k,v in ev.items() if k not in ('stars','forks','open_issues','tree','code_paths','key_files','source_snippets')}
    # 已有人做的 Issue 只留标题和摘要，省 token；候选池保留正文
    listed={i['number'] for i in pool[:45]}
    def body_cap(i):
        return 2200 if i['number'] in listed else (600 if i['number'] in pool_numbers else 300)
    compact['issues']=[dict(i, body=(i.get('body') or '')[:body_cap(i)]) for i in ev.get('issues',[])]
    existing=set(existing or [])
    pool_text='\n'.join(_issue_line(i) for i in pool[:45] if i['number'] not in existing) or '（空）'
    claimed_text='\n'.join(_issue_line(i) for i in claimed[:25]) or '（空）'
    round_text=''
    if existing:
        round_text=f"""

这是补卡轮：前一轮已经出了这些 Issue 的卡：{'、'.join('#'+str(n) for n in sorted(existing))}，不要重复。请只从下面「优先候选池」里再补最多 {need} 张，全部硬约束照旧；候选池里确实没有合适的就返回空数组。"""
    context=''
    if analysis:
        ent=analysis.get('entry',{}); cm=analysis.get('codemap',{}); rb=analysis.get('runbook',{})
        context='\n\n已完成的项目分析（任务卡要与之一致，优先落在 ownership_target、gaps 和 first_prs 指出的方向）：'+json.dumps({'overview':analysis.get('positioning',{}).get('overview'),'modules':cm.get('modules'),'hotspots':cm.get('hotspots'),'gaps':ent.get('gaps'),'ownership_target':ent.get('ownership_target'),'first_prs':ent.get('first_prs'),'no_gpu_paths':rb.get('no_gpu_paths')},ensure_ascii=False)
    return PROFILE+context+round_text+f'''

优先候选池（无人认领、时间线里没有 open PR，按更新时间新→旧排列；任务卡优先从这里出，尤其是能用上候选人专长、又能在 Mac 上复现的）：
{pool_text}

已有人在做（有 assignee 或 open PR）：这些最多只能出「去 review / 补测试」的卡，而且全库合计不超过 2 张：
{claimed_text}
'''+'''

为下面这个开源仓库生成“可直接开工、并且知道怎么得体介入”的贡献任务卡。
算力约束再强调一次：**目前没有任何 GPU**。任务必须能在 CPU / Apple Silicon 上开发、复现和验证；最多允许用 Colab 免费 T4 做几十分钟的最终确认。
因此不要推荐：需要特定架构（SM120 / Hopper / Blackwell）才能复现的 bug、需要 A100 / H100 或多卡的性能问题、需要长时间训练的任务。
仍然能发挥专长的方向：算子的数值正确性与 CPU 参考实现、Triton 代码生成与编译期问题（Triton 解释器模式 TRITON_INTERPRET=1 可在 CPU 跑）、CUDA 代码审阅与编译期修复（Colab 上 nvcc 可验证）、性能建模与 roofline 分析、调度器 / 内存管理 / 权重加载等纯逻辑层、构建系统与多后端适配、文档和测试基建。

硬约束：
1. 每张卡必须绑定输入 issues 中一个真实、仍开放的 Issue；source_url、source_number、source_title 必须逐字取自输入，禁止虚构。
2. 介入是否得体是第一优先级：Issue 已有 assignees、或 linked_prs 里有 open 状态的 PR、或 pulls 里明显已覆盖 → 不要推荐去做，最多建议去 review / 补测试；在 engagement 字段写清楚判断依据。
3. compute_class 只能填 "CPU"、"Mac"、"Colab T4" 三者之一，写明验证路径；任何需要真机 GPU 才能复现或验证的任务直接不要生成。优先能发挥候选人 kernel / 性能专长、且维护者明显关心（评论多、最近更新、有 label）的任务。普通仓库最多 6 张；focus=true 的重点仓库最多 12 张、候选池够的话不少于 8 张，要把候选池用足（包括 Roadmap / Tracking 子项）。宁缺毋滥；没有可靠任务返回空数组。
3a. 每张卡 kind 填 "issue"。[Roadmap] / [Tracking] / [RFC] 这类 Issue 也算：从它正文的未勾选子项里挑一个具体子任务成卡，source 仍是这个 Issue，title 和 claim_comment 里点名子项。
3b. young=true（年轻仓库，Issue 很少）额外允许 kind="proposal" 的提案卡，最多 5 张：不绑 Issue，依据 README、根目录、最近 commits 提出具体、可验证、维护者大概率想要的改进（补测试、CPU/Metal 后端正确性对照、文档与示例、性能基线脚本、构建与 CI）。提案卡的 source_url 必须是 commits 里某条 commit 的 url 或仓库 url，source_number 填 0，source_title 填该 commit message 或仓库名；engagement 必须写明「先开 Issue 提案，得到回应再动手」；claim_comment 改写成一段英文的 Issue 草稿（第一行是标题）。
4. 实施步骤具体到调查、代码修改、测试与提交前沟通；likely_paths 只能依据 README、CONTRIBUTING、Issue 正文和根目录推断，不确定就写“需先定位”。
5. validation 写可执行的验收方式；questions 写开工前应在 Issue 询问维护者的问题。
6. claim_comment：一段英文、可直接贴到该 Issue 下的认领留言，礼貌、具体、不超过 120 词：说明理解、打算怎么做、需要维护者确认什么、大约多久出 PR。不要提候选人的个人经历。
7. pr_scope：一句话说明第一个 PR 该多小、边界在哪；time_estimate：诚实的工时估计，如「2–3 个晚上」。skill_fit：一句话说这张卡用到候选人哪项专长。
8. how_to_engage（仓库级）：3–5 条，基于 CONTRIBUTING 和 README：在哪讨论（community 链接）、PR 前要不要先开 Issue / RFC、CLA / DCO、测试和格式要求、维护者响应节奏。没有依据的不要写。
9. why_core 解释它如何通向长期维护职责，不写空泛鼓励。recommended_order 使用任务标题给出建议顺序。
10. 全部字段中文输出（title 也要中文），代码、文件名、专有名词保留原文；只有 claim_comment 用英文。
11. local_repro：一到三行，写清楚在这台没有 GPU 的 MacBook 上怎么复现问题或验证改动（具体命令、环境变量、要跑的测试文件）。写不出来就说明这张卡其实需要 GPU，不要出。以下这些事情的核心在 CUDA 运行时，Mac 上根本跑不到，不要给它们标 CPU / Mac：memory saver（release_memory_occupation / resume_memory_occupation）、CUDA Graph 捕获、LD_PRELOAD 劫持 cudaMalloc、NCCL 通信、显存占用测量、nvidia-smi、CUDA 流调度。
12. validation 里引用尚不存在、由这张卡新建的文件时注明「新增」；不要把待新建的测试写成已经存在。
13. 安装脚本、包管理器、系统权限这类环境问题（Homebrew、pip 依赖冲突、macOS xattr / Gatekeeper、CI runner 配置）不是核心贡献，也用不上候选人的专长：不要为它们出卡，除非维护者明确标了 help wanted；即便出卡 priority 也只能是 low。

仓库证据：'''+json.dumps(compact,ensure_ascii=False)


ENV_ONLY=re.compile(r'homebrew|\bbrew\b|portable-ruby|install\.sh|xattr|gatekeeper|provenance|安装脚本|环境问题|pip 依赖|conda', re.I)
GPU_ONLY=re.compile(r'memory.?saver|release_memory_occupation|resume_memory_occupation|LD_PRELOAD|cuda.?graph|\bnccl\b|nvidia-smi|cudaMalloc|torch\.cuda\.|cuda stream|CUDA 流', re.I)
REVIEW_CAP=2


def _priority_rank(task):
    return {'high':0,'高':0,'优先':0,'medium':1,'中':1,'low':2,'低':2}.get(str(task.get('priority','')).lower(),1)


def valid_tasks(generated,evidence):
    """把模型给的卡过一遍硬规则：Issue 必须真实、算力必须无 GPU 可做、review 卡限量。"""
    allowed={i['url']:i for i in evidence.get('issues',[])}; clean=[]; proposals=[]
    proposal_sources={evidence.get('url')} | {c.get('url') for c in evidence.get('commits',[]) if c.get('url')}
    for task in generated.get('tasks',[]):
        cc=str(task.get('compute_class','')).strip()
        howto=' '.join([task.get('local_repro','') or '', task.get('first_action','') or '', ' '.join(task.get('implementation_steps') or []), ' '.join(task.get('validation') or [])])
        if str(task.get('kind','')).lower()=='proposal':
            if not evidence.get('young') or task.get('source_url') not in proposal_sources:
                print(f"丢弃无依据的提案卡：{task.get('title')}"); continue
            if cc not in ('CPU','Mac','Colab T4'): continue
            if cc!='Colab T4' and GPU_ONLY.search(howto):
                print(f"丢弃实际需要 CUDA 运行时的提案卡：{task.get('title')}"); continue
            task['issue_status']={'assignees':[],'comments':0,'labels':['提案'],'updated_at':'','created_at':'','open_prs':[],'proposal':True}
            proposals.append(task); continue
        source=allowed.get(task.get('source_url'))
        if not source or task.get('source_number')!=source['number']: continue
        if cc not in ('CPU','Mac','Colab T4'):
            print(f"丢弃需要 GPU 的任务：{task.get('title')}（{cc} / {task.get('compute')}）"); continue
        if re.search(r'sm_?\d{2,3}|hopper|blackwell|h100|a100|多卡|multi-?gpu|nvlink', (task.get('title','')+' '+task.get('compute','')), re.I):
            print(f"丢弃硬件绑定任务：{task.get('title')}"); continue
        if cc!='Colab T4' and GPU_ONLY.search(howto):
            print(f"丢弃实际需要 CUDA 运行时的任务：{task.get('title')}（{GPU_ONLY.search(howto).group(0)}）"); continue
        if cc!='Colab T4' and len((task.get('local_repro') or '').strip())<8:
            print(f"丢弃没有本机复现路径的任务：{task.get('title')}"); continue
        if ENV_ONLY.search(task.get('title','')+' '+source.get('title','')+' '+task.get('goal','')):
            if 'help wanted' not in ' '.join(source.get('labels') or []).lower():
                print(f"丢弃环境 / 安装类任务：{task.get('title')}"); continue
            task['priority']='low'
        task['source_title']=source['title']
        open_prs=[p for p in source.get('linked_prs',[]) if p.get('state')=='open']
        task['issue_status']={'assignees':source.get('assignees',[]),'comments':source.get('comments',0),'labels':source.get('labels',[]),
                              'updated_at':source.get('updated_at'),'created_at':source.get('created_at'),'open_prs':open_prs}
        task['review_only']=bool(source.get('assignees') or open_prs)
        clean.append(task)
    # 去 review 别人 PR 的卡最多 REVIEW_CAP 张（按优先级留）
    reviews=sorted([t for t in clean if t.get('review_only')], key=_priority_rank)
    dropped=reviews[REVIEW_CAP:]
    for t in dropped: print(f"review 卡超出上限，丢弃：{t.get('title')}")
    clean=[t for t in clean if t not in dropped]
    limit=12 if evidence.get('focus') else 6
    generated['tasks']=clean[:limit]+proposals[:5]
    return generated


def merge_tasks(generated, extra, evidence):
    """把补卡轮的结果并进来：不重复 source_number，review 卡总数仍受上限约束。"""
    have={t.get('source_number') for t in generated.get('tasks',[]) if t.get('kind')!='proposal'}
    reviews=sum(1 for t in generated.get('tasks',[]) if t.get('review_only'))
    added=0
    for t in extra.get('tasks',[]):
        if str(t.get('kind','')).lower()=='proposal' or t.get('source_number') in have: continue
        if t.get('review_only'):
            if reviews>=REVIEW_CAP: continue
            reviews+=1
        generated['tasks'].append(t); have.add(t.get('source_number')); added+=1
    limit=12 if evidence.get('focus') else 6
    issues=[t for t in generated['tasks'] if str(t.get('kind','')).lower()!='proposal'][:limit]; props=[t for t in generated['tasks'] if str(t.get('kind','')).lower()=='proposal']
    generated['tasks']=issues+props
    return added


CHANNEL_TOKEN=re.compile(r'#[A-Za-z][\w-]{2,}')


def scrub_channels(items, corpus):
    """去掉提到证据里不存在的聊天频道名（#xxx）的条目：模型爱编 Slack 频道。"""
    kept=[]
    for item in items or []:
        text=str(item)
        if any(tok.lower() not in corpus for tok in CHANNEL_TOKEN.findall(text)):
            print(f"去掉编造的频道：{text[:60]}"); continue
        kept.append(item)
    return kept


def analyze_repo(name, opts=None):
    """单个仓库：抓证据 → Gemini 出卡 → 校验。返回 (结果 or None, 失败详情 or None)。"""
    try:
        evidence=collect_repo(name, opts)
        label='contribution-'+name.replace('/','-')
        analysis, models=run_analysis(evidence, label)
        system='你是资深开源维护者与 AI 系统工程师。把真实 GitHub Issue 变成严谨、可执行、可验证的贡献计划。'
        generated=radar.call_llm_json(system,task_prompt(evidence, analysis),REPO_SCHEMA,label=label+'-tasks')
        if not generated: raise RuntimeError('GeminiGenerationFailed')
        generated['repo']=name; generated=valid_tasks(generated,evidence)
        models['tasks']=radar.LAST_MODEL_USED
        # 重点仓库不满 8 张、普通仓库不满 4 张：只拿剩余候选池再补一轮
        target=8 if evidence.get('focus') else 4
        issue_cards=[t for t in generated['tasks'] if str(t.get('kind','')).lower()!='proposal']
        remaining=[i for i in candidate_pool(evidence) if i['number'] not in {t.get('source_number') for t in issue_cards}]
        if len(issue_cards)<target and remaining:
            extra=radar.call_llm_json(system,task_prompt(evidence, analysis, existing=[t.get('source_number') for t in issue_cards], need=target-len(issue_cards)),TOPUP_SCHEMA,label=label+'-tasks-topup')
            if extra:
                extra=valid_tasks(dict(extra, tasks=extra.get('tasks',[])), evidence)
                added=merge_tasks(generated, extra, evidence)
                models['tasks-topup']=radar.LAST_MODEL_USED
                print(f"{name}: 补卡轮新增 {added} 张")
        corpus=' '.join([evidence.get('readme') or '', evidence.get('contributing') or '', ' '.join(evidence.get('community') or [])]).lower()
        generated['how_to_engage']=scrub_channels(generated.get('how_to_engage'), corpus)
        if isinstance(analysis.get('community'),dict):
            analysis['community']['channels']=scrub_channels(analysis['community'].get('channels'), corpus)
        generated['analysis']=analysis
        generated['evidence']={k:v for k,v in evidence.items() if k not in ('readme','key_files','code_paths','source_snippets')}
        generated['models']=models
        generated['model']=summarize_models(models)
        return generated, None
    except Exception as exc:
        detail=type(exc).__name__
        if isinstance(exc, urllib.error.HTTPError): detail=f'HTTP {exc.code} {exc.url[:80]}'
        elif str(exc): detail=f'{detail}: {str(exc)[:120]}'
        print(f'仓库失败 {name}: {detail}')
        return None, {'repo':name,'error':detail}


def summarize_global_model(repos):
    """全站一句话：主力模型 + 有几个仓库的哪些阶段降级了。"""
    stage_models={}
    for r in repos:
        for k,m in (r.get('models') or {'all':r.get('model','')}).items():
            if m: stage_models.setdefault(m,[]).append((r.get('repo',''),k))
    if not stage_models: return ''
    main=max(stage_models, key=lambda m: len(stage_models[m]))
    others=[(m,v) for m,v in stage_models.items() if m!=main]
    if not others: return main
    note='；'.join(f'{len({repo for repo,_ in v})} 个仓库的 {len(v)} 个阶段降级到 {m}' for m,v in others)
    return f'{main}（{note}）'


def assemble(results, names, previous, planned=None):
    """把各仓库结果按配置顺序拼成 contributions.json；失败的用上次结果并标 stale；本轮没计划跑的原样保留。"""
    old={x.get('repo'):x for x in previous.get('repos',[])}; repos=[]; failures=[]; models=[]
    planned=set(names if planned is None else planned)
    for name in names:
        if name not in planned:
            if name in old: repos.append(old[name]); models.append(old[name])
            continue
        generated, failure = results.get(name, (None, {'repo':name,'error':'NoResult'}))
        if generated:
            repos.append(generated); models.append(generated)
        else:
            failures.append(failure)
            if name in old:
                stale=old[name]; stale['stale']=True; repos.append(stale)
    model=summarize_global_model(models)
    return {'updated':datetime.now(timezone.utc).isoformat(timespec='seconds'),'model':model,'repos':repos,'failures':failures}


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--only', help='只分析这一个仓库（CI 矩阵用）')
    parser.add_argument('--out', help='单仓库结果写到这个 JSON 文件')
    parser.add_argument('--merge', help='把目录下的单仓库 JSON 合并成 contributions.json')
    parser.add_argument('--list', action='store_true', help='输出仓库列表 JSON（CI 矩阵用）')
    parser.add_argument('--focus', action='store_true', help='配合 --list：只列重点仓库')
    parser.add_argument('--scope', default='all', choices=['all','focus'], help='配合 --merge：本轮只跑了哪些仓库，其余原样保留')
    args=parser.parse_args()
    entries=[repo_options(e) for e in json.loads(CONFIG.read_text())]
    names=[e['repo'] for e in entries]; options={e['repo']:e for e in entries}
    focus_names=[e['repo'] for e in entries if e['focus']]
    if args.list:
        print(json.dumps(focus_names if args.focus else names)); return
    previous=json.loads(DATA.read_text()) if DATA.exists() else {'repos':[]}
    if args.only:
        generated, failure = analyze_repo(args.only, options.get(args.only))
        out=Path(args.out or f"/tmp/contrib-{slug(args.only)}.json")
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps({'repo':args.only,'result':generated,'failure':failure},ensure_ascii=False))
        print(f"{args.only}: {'ok, '+str(len(generated.get('tasks',[])))+' 张卡' if generated else '失败'}")
        return
    if args.merge:
        results={}
        for f in Path(args.merge).rglob('*.json'):
            try:
                d=json.loads(f.read_text())
                if d.get('repo'): results[d['repo']]=(d.get('result'), d.get('failure'))
            except Exception as exc:
                print(f'读取 {f} 失败：{exc}')
    else:
        results={name: analyze_repo(name, options.get(name)) for name in names}
    out=assemble(results, names, previous, planned=focus_names if (args.merge and args.scope=='focus') else None)
    DATA.parent.mkdir(parents=True,exist_ok=True); DATA.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(f'贡献任务：{len(out["repos"])} 个仓库，{sum(len(x.get("tasks",[])) for x in out["repos"])} 张卡片；失败 {len(out["failures"])}；模型 {out["model"]}')


def esc(value,quote=False):
    """转义后再还原 **粗体** 和 `代码` 两种模型爱用的 markdown。"""
    text=html.escape(str(value or ''),quote=quote)
    text=re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text=re.sub(r'`([^`\n]+?)`', r'<code>\1</code>', text)
    return text
def slug(repo): return re.sub(r'[^a-z0-9._-]+','-',repo.lower().replace('/','--')).strip('-')
def list_html(items): return '<ul>'+''.join(f'<li>{esc(x)}</li>' for x in items)+'</ul>'


def status_badges(task):
    st=task.get('issue_status') or {}
    badges=[]
    if st.get('proposal'): badges.append('<span class="badge warn">提案 · 需先开 Issue</span>')
    if st.get('assignees'): badges.append(f'<span class="badge warn">已指派 {esc(", ".join(st["assignees"]))}</span>')
    if st.get('open_prs'): badges.append(f'<span class="badge warn">已有 PR #{esc(st["open_prs"][0].get("number"))}</span>')
    if not st.get('proposal') and not st.get('assignees') and not st.get('open_prs'): badges.append('<span class="badge ok">无人认领</span>')
    if st.get('comments') is not None: badges.append(f'<span class="badge">{st.get("comments",0)} 条评论</span>')
    for label in (st.get('labels') or [])[:3]: badges.append(f'<span class="badge">{esc(label)}</span>')
    if st.get('updated_at'): badges.append(f'<span class="badge">更新 {esc(st["updated_at"][:10])}</span>')
    return ''.join(badges)


def task_card(task,index):
    priority={'high':'优先','medium':'可选','low':'候补'}.get(str(task.get('priority','')).lower(),task.get('priority',''))
    claim=task.get('claim_comment','')
    return f'''<article class="task-card"><div class="task-top"><span class="task-index">任务 {index}</span><span>{esc(priority)} · {esc(task.get('difficulty'))} · <b>{esc(task.get('compute_class') or task.get('compute'))}</b> · {esc(task.get('time_estimate'))}</span></div>
<h2>{esc(task.get('title'))}</h2><p class="source-link"><a href="{esc(task.get('source_url'),True)}" rel="noopener noreferrer">{('依据：' if str(task.get('kind','')).lower()=='proposal' else 'Issue #'+str(task.get('source_number'))+' · ')}{esc(task.get('source_title'))} ↗</a></p>
<p class="badges">{status_badges(task)}</p>
<p><b>用到的专长：</b>{esc(task.get('skill_fit'))}</p><p><b>目标：</b>{esc(task.get('goal'))}</p><p><b>为什么值得长期做：</b>{esc(task.get('why_core'))}</p>
<div class="engage"><b>怎么介入：</b>{esc(task.get('engagement'))}<br><b>第一个 PR 的边界：</b>{esc(task.get('pr_scope'))}</div>
<div class="first-action"><b>第一步：</b>{esc(task.get('first_action'))}</div>{('<div class="first-action"><b>本机怎么复现 / 验证：</b>'+esc(task.get('local_repro'))+'</div>') if task.get('local_repro') else ''}
<details open><summary>{'Issue 草稿（英文，先开 Issue 讨论）' if str(task.get('kind','')).lower()=='proposal' else '认领留言（英文，可直接贴到 Issue）'}</summary><pre class="claim" data-claim>{esc(claim)}</pre><button type="button" class="btn-sm" data-copy-claim>复制留言</button></details>
<details><summary>大致实施方案</summary>{list_html(task.get('implementation_steps',[]))}</details><details><summary>可能涉及的目录或文件</summary>{list_html(task.get('likely_paths',[]))}</details>
<details><summary>验收方式</summary>{list_html(task.get('validation',[]))}</details><details><summary>开工前问题与风险</summary><h3>向维护者确认</h3>{list_html(task.get('questions',[]))}<h3>风险</h3>{list_html(task.get('risks',[]))}</details></article>'''


def _rows(items, *cols):
    return ''.join('<tr>'+''.join(f'<td>{esc(it.get(c))}</td>' for c in cols)+'</tr>' for it in (items or []))


def _kv_list(items, a, b):
    return '<ul>'+''.join(f'<li><b>{esc(it.get(a))}</b>：{esc(it.get(b))}</li>' for it in (items or []))+'</ul>'


def _check(items):
    return '<ul class="checklist">'+''.join(f'<li><label><input type="checkbox"> {esc(x)}</label></li>' for x in (items or []))+'</ul>'


def _tw(text, size=13):
    """估算文本像素宽：汉字按一个字号，ASCII 按 0.56 字号。"""
    return sum(size if ord(ch) > 0x2E7F else size*0.56 for ch in str(text or ''))


def _svg_text(x, y, text, cls='', anchor='middle'):
    return f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="{anchor}" class="{cls}">{esc(text)}</text>'


def arch_svg(diagram, modules):
    """分层架构图：每层一行，模块是方框，依赖是带箭头的曲线。没有可用数据返回空串。"""
    if not isinstance(diagram, dict): return ''
    known=[m.get('module','') for m in (modules or []) if m.get('module')]
    placed=set(); layers=[]
    for layer in diagram.get('layers') or []:
        names=[n.strip() for n in re.split(r'[,，、;；/]', str(layer.get('modules',''))) if n.strip()]
        names=[n for n in names if n in known and n not in placed]
        if not names: continue
        placed.update(names); layers.append((layer.get('name','') or '', names))
    rest=[n for n in known if n not in placed]
    if rest: layers.append(('其他', rest))
    if len(layers) < 2: return ''
    neigh={}
    for e in diagram.get('edges') or []:
        a,b=str(e.get('from','')).strip(), str(e.get('to','')).strip()
        if a in placed and b in placed:
            neigh.setdefault(a,set()).add(b); neigh.setdefault(b,set()).add(a)
    order={}
    for li,(lname,names) in enumerate(layers):
        if li:
            orig={n:i for i,n in enumerate(names)}   # list.sort 期间 names 是空的，不能在 key 里 index
            def bary(n):
                xs=[order[m] for m in neigh.get(n,()) if m in order]
                return (sum(xs)/len(xs)) if xs else orig[n]
            names=sorted(names, key=bary); layers[li]=(lname,names)
        for i,n in enumerate(names): order[n]=i-(len(names)-1)/2
    W=720; label_w=118; x0=label_w+14; x1=W-14; gap=12; bh=40; fs=13
    pos={}; bands=[]; y=14
    for lname, names in layers:
        rows=[[]]; used=0
        for n in names:
            bw=min(max(_tw(n, fs)+26, 96), 250)
            if used and used+gap+bw > x1-x0: rows.append([]); used=0
            rows[-1].append((n,bw)); used+= (gap if used else 0)+bw
        top=y
        for row in rows:
            total=sum(bw for _,bw in row)+gap*(len(row)-1); x=x0+((x1-x0)-total)/2
            for n,bw in row:
                pos[n]=(x,y+8,bw,bh); x+=bw+gap
            y+=bh+18
        bands.append((lname, top, y-10)); y+=30
    H=y-16
    out=[f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="架构图">',
         '<defs><marker id="arw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="d-arrow"/></marker></defs>']
    for i,(lname,top,bottom) in enumerate(bands):
        out.append(f'<rect x="6" y="{top:.0f}" width="{W-12}" height="{bottom-top:.0f}" rx="8" class="d-band{i%2}"/>')
        out.append(_svg_text(12, (top+bottom)/2+4, lname[:9], 'd-layer', 'start'))
    edges=[]
    for e in diagram.get('edges') or []:
        a,b=str(e.get('from','')).strip(), str(e.get('to','')).strip()
        if a in pos and b in pos and a!=b: edges.append((a,b,str(e.get('label',''))[:10]))
    for a,b,label in edges[:24]:
        ax,ay,aw,ah=pos[a]; bx,by,bw,bh2=pos[b]
        if by > ay+ah-1:   # 向下
            sx,sy,ex,ey=ax+aw/2, ay+ah, bx+bw/2, by
        elif by+bh2 < ay+1: # 向上
            sx,sy,ex,ey=ax+aw/2, ay, bx+bw/2, by+bh2
        else:               # 同一层
            sx,sy,ex,ey=(ax+aw, ay+ah/2, bx, by+bh2/2) if bx>ax else (ax, ay+ah/2, bx+bw, by+bh2/2)
        mx,my=(sx+ex)/2,(sy+ey)/2
        same_layer = not (by > ay+ah-1 or by+bh2 < ay+1)
        cx,cy=(mx, my-34) if same_layer else (mx, my)
        upward = by+bh2 < ay+1
        out.append(f'<path d="M{sx:.0f} {sy:.0f} Q{cx:.0f} {cy:.0f} {ex:.0f} {ey:.0f}" class="d-edge{" d-back" if upward else ""}" marker-end="url(#arw)"/>')
        length=((ex-sx)**2+(ey-sy)**2)**0.5
        if label and length >= 34:
            lx,ly=(sx+2*cx+ex)/4, (sy+2*cy+ey)/4
            out.append(_svg_text(lx+8, ly-4 if same_layer else ly+4, label, 'd-elabel', 'start'))
    for n,(x,yy,bw,bh_) in pos.items():
        out.append(f'<g><title>{esc(n)}</title><rect x="{x:.0f}" y="{yy:.0f}" width="{bw:.0f}" height="{bh_}" rx="7" class="d-box"/>{_svg_text(x+bw/2, yy+bh_/2+5, n if _tw(n,fs)<=bw-16 else n[:max(3,int((bw-30)/fs))]+"…", "d-mod")}</g>')
    out.append('</svg>')
    cap=diagram.get('caption') or ''
    return f'<figure class="diagram"><div class="diagram-wrap arch">{"".join(out)}</div>{("<figcaption>"+esc(cap)+"</figcaption>") if cap else ""}</figure>'


def flow_svg(flow):
    """一次请求的流程图：竖排编号方框，箭头向下。"""
    steps=[f for f in (flow or []) if isinstance(f, dict) and f.get('step')]
    if len(steps) < 3: return ''
    W=640; bh=58; gap=26; H=14+len(steps)*(bh+gap)-gap+14
    out=[f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="调用流程图">',
         '<defs><marker id="arw2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="d-arrow"/></marker></defs>']
    y=14
    for i,f in enumerate(steps):
        out.append(f'<rect x="40" y="{y}" width="{W-54}" height="{bh}" rx="8" class="d-box"/>')
        out.append(f'<circle cx="40" cy="{y+bh/2:.0f}" r="14" class="d-num"/>{_svg_text(40, y+bh/2+5, str(i+1), "d-numtext")}')
        out.append(_svg_text(66, y+23, str(f.get('step',''))[:24], 'd-step', 'start'))
        comp=str(f.get('component',''))[:40]; path=str(f.get('path',''))[:60]
        out.append(_svg_text(66, y+44, (comp+('  ·  '+path if path else ''))[:88], 'd-sub', 'start'))
        if i < len(steps)-1:
            out.append(f'<path d="M{W/2:.0f} {y+bh} L{W/2:.0f} {y+bh+gap-2}" class="d-edge" marker-end="url(#arw2)"/>')
        y+=bh+gap
    out.append('</svg>')
    return f'<figure class="diagram"><div class="diagram-wrap">{"".join(out)}</div></figure>'


def analysis_html(a, ev):
    if not a: return ''
    if 'positioning' not in a:  # 旧版单块结构，直接跳过
        return ''
    P,C,R,M,E=(a.get(k,{}) for k in ('positioning','codemap','runbook','community','entry'))
    tree=ev.get('tree') or {}
    tree_html=''.join(f'<li><code>{esc(k)}/</code> <span class="muted">{v.get("files",0)} 个文件</span>'+(f'<br><span class="muted">{esc(", ".join(v.get("children",[])[:14]))}</span>' if v.get('children') else '')+'</li>' for k,v in sorted(tree.items(), key=lambda kv:-kv[1].get('files',0))[:16])
    toc='<nav class="toc"><b>目录</b> <a href="#ch1">一、项目定位</a> · <a href="#ch2">二、架构与代码地图</a> · <a href="#ch3">三、本地跑起来</a> · <a href="#ch4">四、维护者与社区</a> · <a href="#ch5">五、切入方案</a> · <a href="#ch6">六、怎么介入</a> · <a href="#ch7">七、任务卡</a></nav>'
    ch1=f'''<section class="analysis" id="ch1"><h2>一、项目定位</h2><p class="overview">{esc(P.get('overview'))}</p>
<h3>解决什么问题、给谁用</h3><p>{esc(P.get('problem'))}</p><p>{esc(P.get('users'))}</p>
<h3>同类项目与差别</h3>{_kv_list(P.get('landscape'),'project','difference')}
<h3>核心能力</h3><div class="table-wrap"><table class="arch"><thead><tr><th>能力</th><th>在哪</th><th>成熟度</th></tr></thead><tbody>{_rows(P.get('capabilities'),'capability','where','maturity')}</tbody></table></div>
<p><b>阶段：</b>{esc(P.get('stage'))}</p><p><b>技术栈：</b>{esc('；'.join(P.get('stack',[])))}</p><p><b>规模：</b>{esc(P.get('numbers'))}</p></section>'''
    mods=''.join(f'<tr><td><b>{esc(m.get("module"))}</b><br><code>{esc(m.get("path"))}</code><br><span class="muted">{esc(m.get("size"))}</span></td><td>{esc(m.get("role"))}<br><span class="muted">入口：{esc(m.get("entry_points"))}</span><br><span class="muted">依赖：{esc(m.get("depends_on"))}</span>{("<br><span class=muted>"+esc(m.get("notes"))+"</span>") if m.get("notes") else ""}</td></tr>' for m in C.get('modules',[]))
    ch2=f'''<section class="analysis" id="ch2"><h2>二、架构与代码地图</h2><p>{esc(C.get('layers'))}</p>
{arch_svg(C.get('diagram'), C.get('modules'))}
<div class="table-wrap"><table class="arch"><thead><tr><th>模块 / 路径</th><th>职责 · 入口 · 依赖</th></tr></thead><tbody>{mods}</tbody></table></div>
<details><summary>目录树（按文件数）</summary><ul class="tree">{tree_html}</ul></details>
<h3>一次调用怎么流过这些模块</h3><p>{esc(C.get('data_flow'))}</p>
{flow_svg(C.get('flow'))}
<h3>关键类型与函数</h3><div class="table-wrap"><table class="arch"><thead><tr><th>名称</th><th>路径</th><th>用途</th></tr></thead><tbody>{_rows(C.get('key_types'),'name','path','purpose')}</tbody></table></div>
<h3>扩展点</h3>{_kv_list(C.get('extension_points'),'where','how')}
<h3>最近在动的地方</h3>{_kv_list(C.get('hotspots'),'path','why')}
<h3>建议阅读顺序</h3><ol>{''.join(f'<li>{esc(x)}</li>' for x in C.get('reading_order',[]))}</ol></section>'''
    ch3=f'''<section class="analysis" id="ch3"><h2>三、本地跑起来（没有 GPU 的 Mac）</h2><h3>安装</h3><ol>{''.join(f'<li><code>{esc(x)}</code></li>' for x in R.get('install',[]))}</ol>
<h3>哪些路径能真跑</h3><p>{esc(R.get('no_gpu_paths'))}</p>
<h3>最小可运行</h3><ol>{''.join(f'<li><code>{esc(x)}</code></li>' for x in R.get('smoke_test',[]))}</ol>
<h3>测试</h3><p>{esc(R.get('test_suite'))}</p><h3>调试</h3>{list_html(R.get('debug_tips',[]))}<h3>CI</h3><p>{esc(R.get('ci'))}</p><h3>坑</h3>{list_html(R.get('pitfalls',[]))}</section>'''
    ch4=f'''<section class="analysis" id="ch4"><h2>四、维护者与社区</h2><p>{esc(M.get('cadence'))}</p>
<div class="table-wrap"><table class="arch"><thead><tr><th>谁</th><th>角色</th><th>依据</th></tr></thead><tbody>{_rows(M.get('people'),'who','role','evidence')}</tbody></table></div>
<h3>流程与 Review 风格</h3><p>{esc(M.get('process'))}</p><p>{esc(M.get('review_style'))}</p>
<h3>渠道</h3>{list_html(M.get('channels',[]))}<h3>这里的规矩</h3>{list_html(M.get('etiquette',[]))}<h3>维护者现在最想要的帮助</h3>{list_html(M.get('what_they_want',[]))}</section>'''
    plan=''.join(f'<div class="phase"><h3>{label}</h3>{_check(E.get(key,[]))}</div>' for key,label in (('phase_30','第 1–30 天：看懂并露面'),('phase_60','第 31–60 天：稳定产出'),('phase_90','第 61–90 天：接管一块')))
    ch5=f'''<section class="analysis" id="ch5"><h2>五、切入方案</h2><div class="engage"><b>建议长期负责：</b>{esc(E.get('ownership_target'))}<br>{esc(E.get('why_this_target'))}</div>
<h3>它现在缺什么（你无 GPU 也能补）</h3><div class="table-wrap"><table class="arch"><thead><tr><th>缺口</th><th>依据</th><th>为什么是你</th></tr></thead><tbody>{_rows(E.get('gaps'),'gap','evidence','why_you')}</tbody></table></div>
<div class="phases">{plan}</div>
<h3>第一批 PR</h3><div class="table-wrap"><table class="arch"><thead><tr><th>题目</th><th>范围</th><th>为什么安全</th></tr></thead><tbody>{_rows(E.get('first_prs'),'title','scope','why_safe')}</tbody></table></div>
<h3>怎么知道自己站住了</h3>{list_html(E.get('signals_of_progress',[]))}
<details><summary>风险与对策</summary>{_kv_list(E.get('risks'),'risk','mitigation')}</details></section>'''
    return toc+ch1+ch2+ch3+ch4+ch5


def detail_page(repo,updated,global_model):
    ev=repo.get('evidence',{}); tasks=repo.get('tasks',[])
    cards=''.join(task_card(t,i) for i,t in enumerate(tasks,1)) or '<p class="empty-state">当前开放 Issue 中没有足够可靠、适合你设备条件的任务。等待下次更新。</p>'
    stale=' · 本次生成失败，展示上次结果' if repo.get('stale') else ''
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(repo['repo'])} 贡献任务 | Anaxagore</title><meta name="description" content="{esc(repo['repo'])} 的具体开源贡献任务、Issue 链接与实施方案。"><link rel="canonical" href="https://lgystoic.github.io/radar/contributions/{slug(repo['repo'])}/"><link rel="stylesheet" href="../../../site.css"><style>.repo-hero{{padding-bottom:1.5rem;border-bottom:1px solid var(--line)}}.repo-meta,.task-top{{display:flex;gap:.7rem;flex-wrap:wrap;color:var(--muted)}}.task-card{{margin:1.2rem 0;padding:1.25rem;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface)}}.task-card h2{{margin:.45rem 0}}.task-card details{{margin-top:.8rem}}.task-index{{font-weight:700;color:var(--accent)}}.first-action{{margin:1rem 0;padding:.8rem 1rem;background:var(--bg-tint);border-radius:var(--radius)}}.source-link a{{font-weight:650}}.back-link{{display:inline-block;margin-bottom:1rem}}.badges{{display:flex;flex-wrap:wrap;gap:.4rem;margin:.5rem 0}}.badge{{padding:.1rem .55rem;border:1px solid var(--line);border-radius:999px;font-size:.75rem;color:var(--muted)}}.badge.ok{{border-color:#3a7d44;color:#3a7d44}}.badge.warn{{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}}.engage{{margin:.8rem 0;padding:.8rem 1rem;border-left:3px solid var(--accent);background:var(--bg-tint);border-radius:0 var(--radius) var(--radius) 0;line-height:1.7}}.claim{{white-space:pre-wrap;font-family:inherit;font-size:.92rem;line-height:1.6;margin:.5rem 0;padding:.8rem 1rem;background:var(--bg-tint);border-radius:var(--radius)}}.analysis h2{{margin-top:2rem}}.analysis h3{{margin-top:1.2rem;font-size:1.02rem}}.analysis p{{line-height:1.8;color:var(--ink-soft)}}.analysis .overview{{font-size:1.02rem;color:var(--ink)}}.arch{{width:100%;border-collapse:collapse;font-size:.9rem}}.arch th,.arch td{{padding:.55rem .6rem;border-top:1px solid var(--line-soft);vertical-align:top;text-align:left;line-height:1.55}}.arch th{{color:var(--muted);font-size:.75rem;font-family:var(--mono)}}.muted{{color:var(--muted);font-size:.85em}}.tree{{list-style:none;padding:0;columns:2;gap:1.5rem;font-size:.85rem}}.tree li{{margin:.3rem 0;break-inside:avoid}}.phases{{display:grid;grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));gap:1rem;margin-top:1rem}}.phase{{padding:1rem;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface)}}.phase h3{{margin:0 0 .5rem;font-size:.95rem}}.checklist{{list-style:none;padding:0;margin:0}}.checklist li{{margin:.4rem 0;line-height:1.5;font-size:.9rem}}.checklist input{{margin-right:.4rem}}.toc{{margin:1rem 0;padding:.7rem 1rem;border:1px solid var(--line);border-radius:var(--radius);background:var(--bg-tint);font-size:.88rem;line-height:1.8}}.toc a{{color:var(--accent)}}.analysis ol li,.analysis ul li{{margin:.3rem 0;line-height:1.6}}.analysis code{{font-size:.85em}}main.wrap{{overflow-wrap:anywhere}}.diagram{{margin:1.2rem 0;max-width:100%;min-width:0}}.diagram-wrap{{overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}}.diagram svg{{display:block;width:100%;height:auto}}.diagram-wrap.arch svg{{min-width:600px}}.diagram figcaption{{margin-top:.5rem;color:var(--muted);font-size:.85rem;line-height:1.6}}.d-band0{{fill:var(--bg-tint)}}.d-band1{{fill:transparent;stroke:var(--line-soft)}}.d-layer{{font:600 12px var(--mono);fill:var(--muted)}}.d-box{{fill:var(--surface);stroke:var(--line);stroke-width:1.2}}.d-mod{{font:600 13px system-ui,sans-serif;fill:var(--ink)}}.d-edge{{fill:none;stroke:var(--accent);stroke-width:1.4;opacity:.85}}.d-back{{stroke-dasharray:5 4;opacity:.6}}.d-arrow{{fill:var(--accent)}}.d-elabel{{font:11px system-ui,sans-serif;fill:var(--ink-soft);paint-order:stroke;stroke:var(--bg);stroke-width:3px}}.d-num{{fill:var(--accent)}}.d-numtext{{font:700 13px var(--mono);fill:#fff}}.d-step{{font:600 14px system-ui,sans-serif;fill:var(--ink)}}.d-sub{{font:12px var(--mono);fill:var(--muted)}}@media (max-width:560px){{.tree{{columns:1}}}}</style></head><body><!-- build:header --><!-- /build:header --><main class="wrap"><a class="back-link" href="../">← 所有项目</a><section class="repo-hero"><p class="kicker">Contribution Tasks</p><h1>{esc(repo['repo'])}</h1><p>{esc(repo.get('fit'))}</p><p><b>当前方向：</b>{esc(repo.get('current_direction'))}</p><div class="repo-meta"><span>★ {ev.get('stars',0)}</span><span>Fork {ev.get('forks',0)}</span><span>{len(tasks)} 个候选任务</span><span>Gemini：{esc(repo.get('model') or global_model)}</span></div><p class="radar-stats">更新于 {esc(updated)}{stale} · <a href="{esc(ev.get('url','#'),True)}" rel="noopener noreferrer">打开仓库 ↗</a></p></section>{analysis_html(repo.get('analysis'), ev)}<section id="ch6"><h2>六、怎么介入这个项目</h2>{list_html(repo.get('how_to_engage',[]))}{('<p><b>社区入口：</b>'+' · '.join(f'<a href="{esc(u,True)}" rel="noopener noreferrer">{esc(u.split("//",1)[-1][:40])}</a>' for u in ev.get('community',[]))+'</p>') if ev.get('community') else ''}<h2>建议顺序</h2>{list_html(repo.get('recommended_order',[]))}<details><summary>成为长期维护者的路径</summary>{list_html(repo.get('maintainer_path',[]))}</details></section><section class="task-grid" id="ch7"><h2>七、任务卡</h2>{cards}</section></main><footer class="site-footer"><div class="wrap"><span>© 2026 Anaxagore</span><span><a href="../../../about/">关于</a></span></div></footer><script src="../../../site.js" defer></script><script>document.querySelectorAll('[data-copy-claim]').forEach(b=>b.addEventListener('click',()=>{{const t=b.parentElement.querySelector('[data-claim]').textContent;const done=()=>{{b.textContent='已复制';setTimeout(()=>b.textContent='复制留言',1500)}};if(navigator.clipboard)navigator.clipboard.writeText(t).then(done,done);else window.prompt('复制',t)}}))</script></body></html>'''


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
            gpu={'CPU':0,'Mac':0,'Colab T4':1}.get(str(t.get('compute_class','')).strip(),2)
            prop=1 if st.get('proposal') else 0
            focus=1 if (r.get('evidence') or {}).get('focus') else 0
            picks.append((pr+hard+gpu+prop-(1 if kernel else 0)-focus, -(st.get('comments') or 0), r['repo'], t))
    picks.sort(key=lambda x:(x[0],x[1]))
    # 三张卡来自三个不同仓库
    seen_repos=set(); distinct=[]
    for item in picks:
        if item[2] in seen_repos: continue
        seen_repos.add(item[2]); distinct.append(item)
    picks=distinct
    if picks:
        parts.append('<section class="picks"><h2>本周先做这三个</h2><p class="radar-stats">全部可在 MacBook / CPU 上完成（最多用 Colab 免费 T4 做最终确认）；无人认领、没有关联 PR、优先级高且能用上 kernel / 性能专长的排在前面。</p><ol class="pick-list">')
        for _,_,repo,t in picks[:3]:
            parts.append(f'<li><a href="./{slug(repo)}/">{esc(repo)}</a> · <a href="{esc(t.get("source_url"),True)}" rel="noopener noreferrer">#{t.get("source_number")}</a> {esc(t.get("title"))}<br><span class="radar-stats">{esc(t.get("difficulty"))} · {esc(t.get("compute"))} · {esc(t.get("time_estimate"))} · {esc(t.get("skill_fit"))}</span></li>')
        parts.append('</ol></section>')
    parts.append('<div class="contribution-grid">')
    for r in d.get('repos',[]):
        ev=r.get('evidence',{}); tasks=r.get('tasks',[]); preview=''.join(f'<li>{esc(t.get("title"))}</li>' for t in tasks[:3])
        an=r.get('analysis') or {}
        blurb=(an.get('positioning') or {}).get('overview') or an.get('overview') or r.get('fit') or ''
        parts.append(f'<article class="contribution-card"><p class="kicker">{len(tasks)} 个候选任务</p><h2><a href="./{slug(r["repo"])}/">{esc(r["repo"])}</a></h2><p>{esc(blurb[:180])}{"…" if len(blurb)>180 else ""}</p><p class="radar-stats">{esc((((r.get("analysis") or {}).get("entry") or {}).get("ownership_target") or "")[:90])}</p><p class="radar-stats">★ {ev.get("stars",0)} · 最近推送 {(ev.get("pushed_at") or "未知")[:10]}</p><ul>{preview}</ul><p><a href="./{slug(r["repo"])}/">查看任务卡与实施方案 →</a></p></article>')
    parts.append('</div>'); return '\n'.join(parts)


if __name__=='__main__': main()
