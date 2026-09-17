#!/usr/bin/env python3
"""Merge liepin-search skill JSON output into the job radar."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from jobs import CONFIG, DATA, match, limit_jobs

ROOT = Path(__file__).resolve().parent.parent


def is_direct_employer_job(job):
    """Keep Liepin company postings and reject anonymous headhunter adverts."""
    url = str(job.get('url') or '')
    parsed = urlparse(url)
    company = str(job.get('company') or '').strip()
    text = ' '.join(str(job.get(k) or '') for k in ('title', 'company', 'compIndustry'))
    if parsed.hostname not in ('www.liepin.com', 'liepin.com'):
        return False
    # Liepin uses /job/<id>.shtml for employer postings and /a/<id>.shtml
    # for anonymous recruiter/headhunter adverts.
    if not re.fullmatch(r'/job/\d+\.shtml', parsed.path):
        return False
    if not company or company == '猎聘企业未公开':
        return False
    if company.startswith('某') or re.search(r'猎头|代招|人才服务|人力资源', text, re.I):
        return False
    return True


def is_headhunter_job(job):
    url = str(job.get('url') or '')
    parsed = urlparse(url)
    return parsed.hostname in ('www.liepin.com', 'liepin.com') and bool(re.fullmatch(r'/a/\d+\.shtml', parsed.path))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', nargs='?', default=str(ROOT / 'radar/data/liepin'))
    parser.add_argument('--failed', action='store_true')
    args = parser.parse_args()
    data = json.loads(DATA.read_text()) if DATA.exists() else {'jobs': [], 'sources': []}
    files = [] if args.failed else sorted(Path(args.directory).glob('*.json'))
    if not files:
        data.setdefault('sources', []).append({'name': '猎聘 · 深圳/北京/上海/杭州/广州', 'ok': False, 'error': 'ExternalToolError'})
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        return

    profile = json.loads(CONFIG.read_text())['profile']
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    # A successful refresh replaces the previous Liepin slice. This also lets
    # tightened quality rules remove old anonymous recruiter rows immediately.
    merged = {j['url']: j for j in data.get('jobs', []) if j.get('source') not in ('liepin', 'liepin-shenzhen')}
    fetched = matched = 0
    for path in files:
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for j in payload.get('results', []):
            fetched += 1
            direct = is_direct_employer_job(j)
            headhunter = is_headhunter_job(j)
            if not direct and not headhunter:
                continue
            url = j.get('url', '')
            row = {
                'title': j.get('title', ''),
                'url': url,
                'location': j.get('location') or '',
                'description': ' '.join(str(v or '') for v in (j.get('salary'), j.get('workYears'), j.get('eduLevel'), j.get('compIndustry'))),
                'source_updated': j.get('date') or '',
                'company': j.get('company') or '猎聘企业未公开',
                'source': 'liepin',
                'listing_type': 'direct' if direct else 'headhunter',
            }
            if not url.startswith('https://'):
                continue
            result = match(row, profile)
            if result:
                result.pop('description', None)
                merged[url] = dict(result, last_seen=now, stale=False)
                matched += 1

    limited = limit_jobs(merged.values(), profile)
    data['jobs'] = limited
    direct_count = sum(j.get('source') == 'liepin' and j.get('listing_type') != 'headhunter' for j in limited)
    headhunter_count = sum(j.get('source') == 'liepin' and j.get('listing_type') == 'headhunter' for j in limited)
    data.setdefault('sources', []).append({'name': '猎聘 · 深圳/北京/上海/杭州/广州', 'ok': True, 'fetched': fetched, 'matched': matched,
                                           'direct': direct_count, 'headhunter': headhunter_count})
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(f'猎聘：原始 {fetched}，匹配 {matched}')


if __name__ == '__main__':
    main()
