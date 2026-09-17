#!/usr/bin/env python3
"""用现有 Gemini 雷达摘要生成学习卡片与小红书草稿，并写入私有 radar-inbox。"""
import base64, json, os, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar import call_llm_json, log

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'radar/data'
SCHEMA = {'type':'object','properties':{'posts':{'type':'array','items':{'type':'object','properties':{'id':{'type':'string'},'headline':{'type':'string'},'takeaways':{'type':'array','items':{'type':'string'}},'post':{'type':'string'}},'required':['id','headline','takeaways','post'],'additionalProperties':False}}},'required':['posts'],'additionalProperties':False}
SYSTEM = '''你是一个技术型小红书作者，读者是想学习 AI 基础设施、GPU kernel、训练/推理加速、DiT 和端侧部署的工程师。根据输入的新闻条目生成学习卡片和可直接修改发布的小红书草稿。不要编造输入没有的事实，不要夸大结论，不要使用“震惊”“天花板”等标题党。headline 12-24字；takeaways 输出2-4条，每条说明一个可学习的技术点；post 350-700字，结构为：标题、开头、发生了什么、为什么值得学、我会怎么验证/实践、结尾提问。保留原文链接，文末加“信息来源：URL”。语气清楚、克制、像工程师分享。'''

def put(repo, path, content, token, message):
    url = f'https://api.github.com/repos/{repo}/contents/{path}'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}', 'Accept':'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r: old = json.load(r); sha = old.get('sha')
    except urllib.error.HTTPError as e:
        if e.code != 404: raise
        sha = None
    body = {'message':message,'content':base64.b64encode(content.encode()).decode()}
    if sha: body['sha'] = sha
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Authorization': f'Bearer {token}', 'Accept':'application/vnd.github+json','Content-Type':'application/json'}, method='PUT')
    with urllib.request.urlopen(req, timeout=30): pass

def main():
    date = os.environ.get('RADAR_DATE') or datetime.now().strftime('%Y-%m-%d')
    src = DATA / f'{date}.json'
    if not src.exists(): raise SystemExit(f'没有 {src}')
    data = json.loads(src.read_text())
    items = [x for x in data.get('items',[]) if x.get('priority') in ('high','medium')]
    items = items[:20]
    if not items: log('[xhs] 没有 high/medium 条目'); return
    prompt = '以下是今日条目 JSON，请逐条生成：\n' + json.dumps([{'id':x.get('id'),'title':x.get('title'),'summary':x.get('summary'),'why':x.get('why'),'link':x.get('link'),'tags':x.get('tags',[])} for x in items], ensure_ascii=False)
    result = call_llm_json(SYSTEM, prompt, SCHEMA, label='xhs')
    if not result: raise SystemExit('Gemini 未返回文稿')
    lines = [f'# AI 信息学习卡片 · {date}', '', '> 自动生成初稿，请人工核对事实和语气后再发布。', '']
    byid = {x['id']:x for x in items}
    for post in result.get('posts',[]):
        src_item = byid.get(post.get('id'), {})
        lines += [f'## {post.get("headline", "")}', '', f'原始条目：{src_item.get("title", "")}', f'链接：{src_item.get("link", "")}', '', '**学习要点**']
        lines += [f'- {x}' for x in post.get('takeaways',[])]
        lines += ['', '**小红书草稿**', '', post.get('post',''), '', '---', '']
    content = '\n'.join(lines)
    out = DATA / f'xhs-{date}.md'; out.write_text(content)
    token, repo = os.environ.get('INBOX_TOKEN','').strip(), os.environ.get('INBOX_REPO','lgyStoic/radar-inbox')
    if token: put(repo, f'posts/{date}.md', content, token, f'AI learning posts: {date}')
    log(f'[xhs] 生成 {len(result.get("posts",[]))} 条，写入 {repo if token else out}')

if __name__ == '__main__': main()
