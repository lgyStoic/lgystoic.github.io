#!/usr/bin/env python3
"""Use job-search-buddy's live URL fetchers to validate/enrich selected ATS jobs."""
import argparse
import json
from pathlib import Path

from jobs import CONFIG, DATA, match


def save_status(data, ok, fetched=0, error=None):
    status = {'name': 'job-search-buddy · URL补全', 'ok': ok}
    status.update({'fetched': fetched, 'matched': fetched} if ok else {'error': error or 'ExternalToolError'})
    data.setdefault('sources', []).append(status)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--failed', action='store_true')
    args = parser.parse_args()
    data = json.loads(DATA.read_text()) if DATA.exists() else {'jobs': [], 'sources': []}
    if args.failed:
        save_status(data, False, error='DependencyInstallError')
        return
    from jobbuddy.core import fetch_from_url, result_to_dict
    profile = json.loads(CONFIG.read_text())['profile']
    count = 0
    for job in data.get('jobs', [])[:12]:
        try:
            detail = result_to_dict(fetch_from_url(job['url']))
            candidate = dict(job, description=detail.get('description') or '')
            candidate['title'] = detail.get('title') or candidate['title']
            candidate['location'] = detail.get('location') or candidate['location']
            updated = match(candidate, profile)
            if updated:
                job.update({k: v for k, v in updated.items() if k in ('title', 'location', 'tags', 'reasons', 'score', 'region')})
                count += 1
        except Exception:
            continue
    save_status(data, True, fetched=count)
    print(f'job-search-buddy：补全 {count} 条')


if __name__ == '__main__':
    main()
