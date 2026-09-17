#!/usr/bin/env python3
"""Official job boards → explainable technical matches → radar/data/jobs.json."""
import argparse
import concurrent.futures
import html
import json
import os
import re
import urllib.request, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'radar/data/jobs.json'
CONFIG = ROOT / 'radar/job_sources.json'


def request(url, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={'User-Agent': 'personal-job-radar/1.0', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def plain(value):
    return ' '.join(html.unescape(re.sub('<[^>]+>', ' ', value or '')).split())


def match(job, profile):
    title = job['title'].lower()
    text = title + ' ' + job.get('description', '').lower()
    if any(term in title for term in profile.get('exclude_title', [])):
        return None
    if profile.get('title_focus') and not any(re.search(r'(?<!\w)' + re.escape(term), title) for term in profile['title_focus']):
        return None
    # Require technical evidence in the title: company-wide descriptions alone are insufficient.
    if not any(term in title for term in profile['title_terms']):
        return None
    tags, reasons, score = [], [], 0
    for group, terms in profile['directions'].items():
        hits = [term for term in terms if re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text, re.I)]
        if hits:
            tags.append(group)
            reasons.append(group + '：' + '、'.join(hits[:3]))
            score += 3 if any(term in title for term in hits) else 1
    if not tags:
        return None
    location = job['location'].lower()
    region = '深圳' if 'shenzhen' in location or '深圳' in location else ('远程' if 'remote' in location else '其他地区')
    if region == '深圳':
        score += 4
    elif region == '远程':
        score += 2
    return dict(job, tags=tags + [region], reasons=reasons, score=score, region=region)


def fetch_source(source):
    rows = []
    if source['kind'] == 'greenhouse':
        payload = request(source['url'] + '?content=true')
        for j in payload['jobs']:
            rows.append({'title': j['title'], 'url': j['absolute_url'], 'location': j['location']['name'], 'description': plain(j.get('content', '')), 'source_updated': j.get('updated_at', '')})
    elif source['kind'] == 'lever':
        payload = request(source['url'])
        for j in payload if isinstance(payload, list) else []:
            cats = j.get('categories', {}) or {}
            rows.append({'title': j.get('text', ''), 'url': j.get('hostedUrl') or j.get('applyUrl', ''), 'location': cats.get('location', ''), 'description': plain(j.get('descriptionPlain') or j.get('description', '')), 'source_updated': ''})
    elif source['kind'] == 'ashby':
        payload = request(source['url'])
        for j in payload.get('jobs', []) if isinstance(payload, dict) else []:
            rows.append({'title': j.get('title', ''), 'url': j.get('jobUrl') or j.get('applyUrl', ''), 'location': j.get('location', ''), 'description': plain(j.get('description', '')), 'source_updated': j.get('publishedAt', '')})
    elif source['kind'] == 'smartrecruiters':
        payload = request(source['url'])
        for j in payload.get('content', []) if isinstance(payload, dict) else []:
            rows.append({'title': j.get('name', ''), 'url': j.get('ref', ''), 'location': (j.get('location') or {}).get('city', ''), 'description': '', 'source_updated': j.get('releasedDate', '')})
    elif source['kind'] == 'workable':
        payload = request(source['url'])
        records = payload.get('jobs', []) if isinstance(payload, dict) else []
        for j in records:
            loc = j.get('location') or {}
            rows.append({'title': j.get('title', ''), 'url': j.get('url', ''), 'location': loc.get('location_str', '') if isinstance(loc, dict) else str(loc), 'description': plain(j.get('description', '')), 'source_updated': j.get('created_at', '')})
    elif source['kind'] == 'recruitee':
        payload = request(source['url'])
        for j in payload.get('offers', []) if isinstance(payload, dict) else []:
            rows.append({'title': j.get('title', ''), 'url': j.get('careers_url') or j.get('url', ''), 'location': j.get('location', ''), 'description': plain(j.get('description', '')), 'source_updated': j.get('published_at', '')})
    elif source['kind'] == 'workday':
        for query in source['queries']:
            offset = 0
            while True:
                payload = request(source['url'], {'appliedFacets': {}, 'limit': 20, 'offset': offset, 'searchText': query})
                postings = payload['jobPostings']
                for j in postings:
                    rows.append({'title': j['title'], 'url': source['base'] + j['externalPath'], 'location': j.get('locationsText', ''), 'description': '', 'source_updated': j.get('postedOn', '')})
                offset += len(postings)
                if offset >= payload['total']:
                    break
                if not postings or offset >= 500:
                    raise ValueError('Incomplete pagination')
    elif source['kind'] == 'page':
        raw = urllib.request.urlopen(urllib.request.Request(source['url'], headers={'User-Agent': 'Mozilla/5.0'}), timeout=25).read().decode('utf-8', 'replace')
        for href, title in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', raw, re.I | re.S):
            title = plain(title)
            if len(title) < 8 or not any(k in title.lower() for k in source.get('title_terms', [])):
                continue
            url = href if href.startswith('http') else source['base'] + href
            rows.append({'title': title, 'url': url, 'location': source.get('location', ''), 'description': title, 'source_updated': ''})
    elif source['kind'] == 'json':
        payload = request(source['url'])
        records = payload if isinstance(payload, list) else payload.get(source.get('items', 'jobs'), [])
        for j in records:
            title = j.get(source.get('title', 'title'), '')
            location = j.get(source.get('location', 'location'), '')
            url = j.get(source.get('url_field', 'url'), '') or j.get('apply_url', '')
            description = plain(j.get(source.get('description', 'description'), ''))
            if title and url:
                rows.append({'title': title, 'url': url, 'location': location if isinstance(location, str) else ', '.join(location or []), 'description': description, 'source_updated': j.get('published_at', '')})
    elif source['kind'] == 'himalayas':
        for query in source['queries']:
            params = urllib.parse.urlencode({'q': query, 'page': 1, 'sort': 'recent'})
            payload = request(source['url'] + '?' + params)
            for j in payload.get('jobs', []):
                restrictions = j.get('locationRestrictions') or []
                rows.append({'title': j.get('title', ''), 'url': 'https://himalayas.app/jobs/' + j.get('slug', ''), 'location': ', '.join(restrictions) or 'Remote', 'description': plain(j.get('excerpt', '')), 'source_updated': j.get('pubDate', '')})
    elif source['kind'] == 'tavily':
        api_key = os.environ.get('BOOLEAN_TAVILY_API_KEY', '').strip()
        if not api_key:
            raise ValueError('BOOLEAN_TAVILY_API_KEY 未配置')
        for query in source['queries']:
            payload = request(source['url'], {'api_key': api_key, 'query': query, 'search_depth': 'advanced', 'max_results': 10, 'include_answer': False})
            for j in payload.get('results', []):
                text = plain(j.get('content', ''))
                location = '深圳 / 香港' if re.search(r'深圳|Shenzhen|香港|Hong Kong', j.get('title', '') + ' ' + text, re.I) else ''
                rows.append({'title': j.get('title', ''), 'url': j.get('url', ''), 'location': location, 'description': text, 'source_updated': ''})
    elif source['kind'] == 'adzuna':
        app_id, app_key = os.environ.get('ADZUNA_APP_ID', '').strip(), os.environ.get('ADZUNA_APP_KEY', '').strip()
        if not app_id or not app_key:
            raise ValueError('ADZUNA_APP_ID/ADZUNA_APP_KEY 未配置')
        for query in source['queries']:
            params = urllib.parse.urlencode({'app_id': app_id, 'app_key': app_key, 'results_per_page': 50, 'what': query, 'where': source['where'], 'content-type': 'application/json'})
            payload = request(f"https://api.adzuna.com/v1/api/jobs/{source['country']}/search/1?{params}")
            for j in payload.get('results', []):
                loc = j.get('location', {}).get('display_name', '') if isinstance(j.get('location'), dict) else ''
                rows.append({'title': j.get('title', ''), 'url': j.get('redirect_url', ''), 'location': loc or source['where'], 'description': plain(j.get('description', '')), 'source_updated': j.get('created', '')})
    else:
        raise ValueError('Unsupported source kind')
    return [dict(j, company=source['name'], source=source['id']) for j in rows]


def collect(config, old, fetcher=fetch_source):
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    jobs, statuses = {}, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [(s, pool.submit(fetcher, s)) for s in config['sources']]
        for source, future in futures:
            try:
                rows = future.result()
                count = 0
                for row in rows:
                    if not row['url'].startswith('https://'):
                        continue
                    if row['company'] in config['profile'].get('excluded_companies', []):
                        continue
                    result = match(row, config['profile'])
                    if result:
                        result.pop('description', None)
                        jobs[result['url']] = dict(result, last_seen=now, stale=False)
                        count += 1
                statuses.append({'name': source['name'], 'ok': True, 'fetched': len(rows), 'matched': count})
            except Exception as exc:
                statuses.append({'name': source['name'], 'ok': False, 'error': type(exc).__name__})
                for previous in old.get('jobs', []):
                    if previous['source'] == source['id']:
                        if previous['company'] in config['profile'].get('excluded_companies', []):
                            continue
                        updated = match(dict(previous, description=' '.join(previous.get('reasons', []))), config['profile'])
                        if updated:
                            updated.pop('description', None)
                            jobs[updated['url']] = dict(updated, stale=True)
    ordered = sorted(jobs.values(), key=lambda j: (j['region'] not in ('深圳', '香港'), j['region'] != '深圳', -j['score'], j['company'], j['title']))
    limited, counts = [], {}
    for job in ordered:
        if counts.get(job['company'], 0) >= config['profile'].get('max_per_company', 3):
            continue
        counts[job['company']] = counts.get(job['company'], 0) + 1
        limited.append(job)
    return {'updated': now, 'sources': statuses, 'jobs': limited, 'search_links': config.get('search_links', [])}


def render():
    data = json.loads(DATA.read_text()) if DATA.exists() else {}
    esc = html.escape
    parts = [f'<p class="radar-stats">最近尝试更新：{esc(data.get("updated", "尚未运行"))} · 按技术关键词与地点排序，不代表录用概率。</p>']
    parts.append('<p>经验、学历、薪资、签证与远程可工作地区未作匹配，请查看职位原文。其他地区包含海外及深圳以外城市；多地点职位请展开原文确认。</p>')
    parts.append('<details><summary>招聘源状态</summary><ul>')
    for s in data.get('sources', []):
        state = f'成功 · {s["fetched"]} 条原始岗位' if s['ok'] else '抓取失败，保留上次结果并标记待复核'
        parts.append(f'<li>{esc(s["name"])}：{state}</li>')
    parts.append('</ul></details>')
    if data.get('search_links'):
        parts.append('<details open><summary>更多招聘网站搜索</summary><ul class="job-search-links">')
        for link in data['search_links']:
            parts.append(f'<li><a href="{esc(link["url"], quote=True)}" rel="noopener noreferrer">{esc(link["name"])}</a> · {esc(link["scope"])}</li>')
        parts.append('</ul></details>')
    groups = [('深圳 / 香港', [j for j in data.get('jobs', []) if j['region'] in ('深圳', '香港')]), ('远程', [j for j in data.get('jobs', []) if j['region'] == '远程']), ('其他地区', [j for j in data.get('jobs', []) if j['region'] == '其他地区'])]
    for label, group in groups:
        if not group: continue
        parts.append(f'<h2>{label} <small>({len(group)})</small></h2><ul class="job-list" data-archive>')
        for job in group:
            search = esc(' '.join([job['title'], job['company'], job['location'], *job['tags']]).lower(), quote=True)
            parts.append(f'<li data-search="{search}" data-tags="{esc("|".join(job["tags"]), quote=True)}"><article><h2><a href="{esc(job["url"], quote=True)}" rel="noopener noreferrer">{esc(job["title"])}</a></h2>')
            parts.append(f'<p>{esc(job["company"])} · {esc(job["location"])} · {esc(job["region"])}</p>')
            parts.append(f'<p>{esc("；".join(job["reasons"]))}</p>')
            state = '待复核：本次来源抓取失败' if job.get('stale') else '最近在招聘列表中发现'
            parts.append(f'<p class="radar-stats">{state} · {esc(job["last_seen"][:10])}</p></article></li>')
        parts.append('</ul>')
    parts.append('<p class="empty-state" data-empty hidden>没有符合当前筛选的岗位。</p>')
    if not data.get('jobs'):
        parts.append('<p>暂未发现符合方向的岗位，请查看招聘源状态；不使用示例岗位填充。</p>')
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text())
    old = json.loads(DATA.read_text()) if DATA.exists() else {}
    result = collect(config, old)
    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        DATA.parent.mkdir(parents=True, exist_ok=True)
        temporary = DATA.with_suffix('.tmp')
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(DATA)
        print(f'岗位：{len(result["jobs"])}；来源成功：{sum(s["ok"] for s in result["sources"])}/{len(result["sources"])}')
    if not any(s['ok'] for s in result['sources']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
