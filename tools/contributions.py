#!/usr/bin/env python3
"""GitHub project signals -> Gemini contribution roadmap -> radar page data."""
import base64
import html
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from radar import call_llm_json

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / 'radar/contribution_repos.json'
DATA = ROOT / 'radar/data/contributions.json'

SCHEMA = {
    'type': 'object',
    'properties': {
        'strategy': {'type': 'string'},
        'repos': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'repo': {'type': 'string'}, 'fit': {'type': 'string'}, 'current_direction': {'type': 'string'},
            'maintainer_signals': {'type': 'array', 'items': {'type': 'string'}},
            'low_compute_options': {'type': 'array', 'items': {'type': 'string'}},
            'gpu_options': {'type': 'array', 'items': {'type': 'string'}},
            'days_30': {'type': 'array', 'items': {'type': 'string'}},
            'days_60': {'type': 'array', 'items': {'type': 'string'}},
            'days_90': {'type': 'array', 'items': {'type': 'string'}},
            'risks': {'type': 'array', 'items': {'type': 'string'}},
        }, 'required': ['repo','fit','current_direction','maintainer_signals','low_compute_options','gpu_options','days_30','days_60','days_90','risks']}},
    }, 'required': ['strategy','repos']
}


def api(path):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'contribution-radar/1.0'}
    token = os.environ.get('GITHUB_TOKEN', '').strip()
    if token: headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request('https://api.github.com/' + path.lstrip('/'), headers=headers)
    with urllib.request.urlopen(req, timeout=25) as response: return json.load(response)


def collect_repo(name):
    meta = api(f'repos/{name}')
    try:
        readme = api(f'repos/{name}/readme')
        text = base64.b64decode(readme.get('content','')).decode('utf-8','replace')[:6000]
    except Exception: text = ''
    issues = api(f'repos/{name}/issues?state=open&sort=updated&per_page=15')
    releases = api(f'repos/{name}/releases?per_page=3')
    commits = api(f'repos/{name}/commits?per_page=12')
    return {
        'repo': name, 'url': meta['html_url'], 'description': meta.get('description'),
        'stars': meta.get('stargazers_count'), 'forks': meta.get('forks_count'),
        'open_issues': meta.get('open_issues_count'), 'pushed_at': meta.get('pushed_at'),
        'readme': text,
        'issues': [{'number':i['number'],'title':i['title'],'labels':[x['name'] for x in i.get('labels',[])],
                    'url':i['html_url'],'is_pr':'pull_request' in i} for i in issues],
        'releases': [{'name':r.get('name') or r.get('tag_name'),'date':r.get('published_at')} for r in releases],
        'commits': [{'message':c['commit']['message'].splitlines()[0],'date':c['commit']['author'].get('date')} for c in commits],
    }


def main():
    names = json.loads(CONFIG.read_text())
    evidence, failures = [], []
    for name in names:
        try: evidence.append(collect_repo(name))
        except Exception as exc: failures.append({'repo':name,'error':type(exc).__name__})
    prompt = '''目标：帮助候选人成为这些项目的 core maintainer，而非刷低质量 PR。候选人方向是 AI Infra、DiT、端侧部署、训练和推理加速，目前没有高性能 GPU。根据仓库的真实 README、近期 issue、commit、release 整理核心 roadmap。不要替候选人决定具体任务，也不要虚构 issue 编号。没有明确 roadmap 时写“根据近期活动推断”。每个项目分别列出多个无 GPU/低算力可验证的贡献方向，以及以后有 GPU 才适合做的方向。低算力方向应包含真正有维护价值的工作，例如 CPU/小模型测试、CI、文档与示例可运行性、接口一致性、错误处理、静态分析、issue 复现与 triage；不要只推荐改错别字。30/60/90 天路线体现从理解项目、稳定贡献到承担 triage/review/release 责任，由候选人自行选择具体切入点。\n\n数据：''' + json.dumps(evidence, ensure_ascii=False)
    result = call_llm_json('你是资深开源维护者和 AI 系统工程师。', prompt, SCHEMA, label='contribution-roadmap')
    if not result: raise SystemExit('Gemini roadmap generation failed')
    by_name = {r['repo']: r for r in evidence}
    for item in result['repos']:
        item['evidence'] = {k:v for k,v in by_name.get(item['repo'],{}).items() if k in ('url','stars','forks','open_issues','pushed_at','issues')}
    out = {'updated':datetime.now(timezone.utc).isoformat(timespec='seconds'),'strategy':result['strategy'],'repos':result['repos'],'failures':failures}
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(f'贡献路线：{len(result["repos"])} 个仓库；失败 {len(failures)}')


def render():
    if not DATA.exists(): return '<p>路线图尚未生成。</p>'
    d=json.loads(DATA.read_text()); e=html.escape
    parts=[f'<p class="radar-stats">更新于 {e(d.get("updated",""))} · Gemini 基于 GitHub 当前公开活动整理</p>',f'<p class="lead-p">{e(d.get("strategy",""))}</p>']
    for r in d.get('repos',[]):
        ev=r.get('evidence',{}); url=ev.get('url','#')
        parts.append(f'<article class="contribution-card"><div class="section-head"><h2><a href="{e(url,quote=True)}" rel="noopener noreferrer">{e(r["repo"])}</a></h2><span>★ {ev.get("stars",0)} · Issue/PR {ev.get("open_issues",0)}</span></div>')
        parts.append(f'<p><b>匹配度：</b>{e(r["fit"])}</p><p><b>当前方向：</b>{e(r["current_direction"])}</p>')
        parts.append('<h3>无 GPU / 低算力可选入口</h3><ul>'+''.join(f'<li>{e(x)}</li>' for x in r.get('low_compute_options',[]))+'</ul>')
        parts.append('<details><summary>需要 GPU 后再考虑</summary><ul>'+''.join(f'<li>{e(x)}</li>' for x in r.get('gpu_options',[]))+'</ul></details>')
        for label,key in [('30 天','days_30'),('60 天','days_60'),('90 天','days_90')]:
            parts.append(f'<h3>{label}</h3><ul>'+''.join(f'<li>{e(x)}</li>' for x in r.get(key,[]))+'</ul>')
        parts.append('<details><summary>维护者信号与风险</summary><ul>'+''.join(f'<li>{e(x)}</li>' for x in r.get('maintainer_signals',[])+r.get('risks',[]))+'</ul></details></article>')
    return '\n'.join(parts)


if __name__ == '__main__': main()
