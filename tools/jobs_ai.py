#!/usr/bin/env python3
"""LLM post-processing: semantic dedupe on domestic direct-employer rows, in chunks."""
import json
from pathlib import Path
from radar import call_llm_json

DATA = Path(__file__).resolve().parent.parent / 'radar/data/jobs.json'
SCHEMA = {'type': 'object', 'properties': {'drop_urls': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['drop_urls']}
CHUNK = 60


def main():
    if not DATA.exists():
        return
    data = json.loads(DATA.read_text())
    jobs = data.get('jobs', [])
    targets = [j for j in jobs if j.get('region') in ('深圳', '香港', '国内') and j.get('listing_type') != 'headhunter']
    if len(targets) < 2:
        return
    drop = set()
    for start in range(0, len(targets), CHUNK):
        chunk = [{'url': j['url'], 'title': j['title'], 'company': j['company'], 'location': j['location']} for j in targets[start:start + CHUNK]]
        prompt = ('下面是同一批招聘岗位。找出「同一家公司、同一个职位」的重复项（标题几乎相同、只是地点或来源不同），'
                  '每组只保留一条，把其余的 URL 放进 drop_urls。不是重复的不要动。\n' + json.dumps(chunk, ensure_ascii=False))
        out = call_llm_json('你是招聘数据清洗器，只做去重，不编造事实。', prompt, SCHEMA, label='jobs-ai')
        if out:
            urls = {c['url'] for c in chunk}
            drop.update(u for u in out.get('drop_urls', []) if u in urls)
    if drop and len(drop) < len(targets) // 2:
        data['jobs'] = [j for j in jobs if j['url'] not in drop]
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        print(f'jobs-ai：去重删除 {len(drop)} 条')


if __name__ == '__main__':
    main()
