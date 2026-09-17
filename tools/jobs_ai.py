#!/usr/bin/env python3
"""Gemini post-processing: semantic dedupe and concise reason cleanup."""
import json
from pathlib import Path
from radar import call_llm_json

DATA = Path(__file__).resolve().parent.parent / 'radar/data/jobs.json'
SCHEMA = {'type':'object','properties':{'keep_urls':{'type':'array','items':{'type':'string'}},'reason_updates':{'type':'object'}},'required':['keep_urls','reason_updates']}

def main():
    if not DATA.exists(): return
    data=json.loads(DATA.read_text()); jobs=data.get('jobs', [])
    if len(jobs) < 2: return
    prompt='对以下岗位做语义去重：同一职位不同来源只保留信息更完整者；不要删除明显不同职位。返回保留的 URL 列表，并可把 reasons 改得更简洁。\n'+json.dumps(jobs,ensure_ascii=False)
    out=call_llm_json('你是招聘数据清洗器，只做去重和措辞优化，不编造事实。',prompt,SCHEMA,label='jobs-ai')
    if not out: return
    keep=set(out.get('keep_urls', [])); by={j['url']:j for j in jobs}
    if keep: data['jobs']=[by[u] for u in keep if u in by]
    for u, reasons in out.get('reason_updates', {}).items():
        if u in by and isinstance(reasons,list): by[u]['reasons']=reasons[:3]
    DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

if __name__ == '__main__': main()
