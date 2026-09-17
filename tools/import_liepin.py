#!/usr/bin/env python3
"""Merge liepin-search skill JSON output into the job radar."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from jobs import CONFIG, DATA, match

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', nargs='?', default=str(ROOT / 'radar/data/liepin'))
    parser.add_argument('--failed', action='store_true')
    args = parser.parse_args()
    data = json.loads(DATA.read_text()) if DATA.exists() else {'jobs': [], 'sources': []}
    files = [] if args.failed else sorted(Path(args.directory).glob('*.json'))
    if not files:
        data.setdefault('sources', []).append({'name': '猎聘 · 深圳', 'ok': False, 'error': 'ExternalToolError'})
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        return

    profile = json.loads(CONFIG.read_text())['profile']
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    merged = {j['url']: j for j in data.get('jobs', [])}
    fetched = matched = 0
    for path in files:
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for j in payload.get('results', []):
            fetched += 1
            url = j.get('url', '')
            row = {
                'title': j.get('title', ''),
                'url': url,
                'location': j.get('location') or '深圳',
                'description': ' '.join(str(v or '') for v in (j.get('salary'), j.get('workYears'), j.get('eduLevel'), j.get('compIndustry'))),
                'source_updated': j.get('date') or '',
                'company': j.get('company') or '猎聘企业未公开',
                'source': 'liepin-shenzhen',
            }
            if not url.startswith('https://'):
                continue
            result = match(row, profile)
            if result:
                result.pop('description', None)
                merged[url] = dict(result, last_seen=now, stale=False)
                matched += 1

    ordered = sorted(merged.values(), key=lambda j: (j['region'] not in ('深圳', '香港'), j['region'] != '深圳', -j['score'], j['company'], j['title']))
    limited, counts = [], {}
    for job in ordered:
        if counts.get(job['company'], 0) >= profile.get('max_per_company', 3):
            continue
        counts[job['company']] = counts.get(job['company'], 0) + 1
        limited.append(job)
    data['jobs'] = limited
    data.setdefault('sources', []).append({'name': '猎聘 · 深圳', 'ok': True, 'fetched': fetched, 'matched': matched})
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(f'猎聘深圳：原始 {fetched}，匹配 {matched}')


if __name__ == '__main__':
    main()
