#!/usr/bin/env python3
"""Merge normalized output from the external ats-jobs package into jobs.json."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from jobs import CONFIG, DATA, match

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', nargs='?', default=str(ROOT / 'radar/data/ats-jobs.json'))
    parser.add_argument('--failed', action='store_true')
    args = parser.parse_args()
    data = json.loads(DATA.read_text()) if DATA.exists() else {'jobs': [], 'sources': []}
    if args.failed:
        data.setdefault('sources', []).append({'name': 'ats-jobs · 12类ATS', 'ok': False, 'error': 'ExternalToolError'})
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        return

    source_rows = json.loads(Path(args.input).read_text())
    profile = json.loads(CONFIG.read_text())['profile']
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    merged = {j['url']: j for j in data.get('jobs', [])}
    matched = 0
    for j in source_rows:
        url = j.get('url', '')
        if not url.startswith('https://'):
            continue
        row = {
            'title': j.get('title', ''),
            'url': url,
            'location': j.get('location', '') or ('Remote' if j.get('remote') else ''),
            'description': j.get('description', '') or '',
            'source_updated': j.get('publishedAt') or j.get('updatedAt') or '',
            'company': j.get('company', '').removeprefix('https://').split('/')[0],
            'source': 'ats-jobs',
        }
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
    data.setdefault('sources', []).append({'name': 'ats-jobs · 12类ATS', 'ok': True, 'fetched': len(source_rows), 'matched': matched})
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(f'ats-jobs：原始 {len(source_rows)}，匹配 {matched}')


if __name__ == '__main__':
    main()
