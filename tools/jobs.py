#!/usr/bin/env python3
"""Official job boards → explainable technical matches → radar/data/jobs.json."""
import argparse
import concurrent.futures
import html
import json
import os
import re
import urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'radar/data/jobs.json'
CONFIG = ROOT / 'radar/job_sources.json'


def request(url, payload=None, headers=None, form=False):
    if payload is None:
        body = None
    elif form:
        body = urllib.parse.urlencode(payload).encode()
    else:
        body = json.dumps(payload).encode()
    base = {'User-Agent': 'Mozilla/5.0 personal-job-radar/1.0', 'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/x-www-form-urlencoded' if form else 'application/json'}
    base.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=base)
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def request_text(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 personal-job-radar/1.0'})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read().decode('utf-8', 'replace')


def plain(value):
    return ' '.join(html.unescape(re.sub('<[^>]+>', ' ', value or '')).split())


CN_CITY_TERMS = ['北京', '上海', '杭州', '广州', '南京', '成都', '武汉', '西安', '苏州', '合肥', '天津', '重庆', '长沙', '厦门', '青岛', '珠海', '东莞', '济南', '郑州', '大连', '中国',
                 'beijing', 'shanghai', 'hangzhou', 'guangzhou', 'nanjing', 'chengdu', 'wuhan', "xi'an", 'xian', 'suzhou', 'hefei', 'tianjin', 'chongqing', 'changsha', 'xiamen', 'qingdao', 'zhuhai', 'dongguan', 'china', 'prc']
REGION_ORDER = {'深圳': 0, '香港': 1, '国内': 2, '远程': 3, '海外': 4}
REGION_BONUS = {'深圳': 4, '香港': 3, '国内': 3, '远程': 2, '海外': 0}


def region_of(location):
    loc = (location or '').lower()
    if 'shenzhen' in loc or '深圳' in loc:
        return '深圳'
    if 'hong kong' in loc or '香港' in loc or 'hongkong' in loc:
        return '香港'
    if any(term in loc for term in CN_CITY_TERMS):
        return '国内'
    if 'remote' in loc or '远程' in loc:
        return '远程'
    return '海外'


def limit_jobs(jobs, profile):
    """深圳 → 香港 → 国内 → 远程 → 海外；每家公司在国内最多 max_per_company_cn 条，海外最多 max_per_company 条。"""
    ordered = sorted(jobs, key=lambda j: (REGION_ORDER.get(j['region'], 9), -j['score'], j['company'], j['title']))
    limited, counts = [], {}
    for job in ordered:
        domestic = job['region'] in ('深圳', '香港', '国内')
        cap = profile.get('max_per_company_cn', 8) if domestic else profile.get('max_per_company', 3)
        key = (job['company'], domestic)
        if counts.get(key, 0) >= cap:
            continue
        counts[key] = counts.get(key, 0) + 1
        limited.append(job)
    return limited


def term_pattern(term):
    """英文词加词边界；中文词没有空格分词，\w 又把汉字算作单词字符，所以直接子串匹配。"""
    if re.search(r'[\u4e00-\u9fff]', term):
        return re.escape(term)
    return r'(?<!\w)' + re.escape(term) + r'(?!\w)'


def match(job, profile):
    title = job['title'].lower()
    text = title + ' ' + job.get('description', '').lower()
    if any(term in title for term in profile.get('exclude_title', [])):
        return None
    if profile.get('title_focus') and not any(re.search(term_pattern(term) if re.search(r'[\u4e00-\u9fff]', term) else r'(?<!\w)' + re.escape(term), title) for term in profile['title_focus']):
        return None
    # Require technical evidence in the title: company-wide descriptions alone are insufficient.
    if not any(term in title for term in profile['title_terms']):
        return None
    tags, reasons, score = [], [], 0
    for group, terms in profile['directions'].items():
        hits = [term for term in terms if re.search(term_pattern(term), text, re.I)]
        if hits:
            tags.append(group)
            reasons.append(group + '：' + '、'.join(hits[:3]))
            score += 3 if any(term in title for term in hits) else 1
    if not tags:
        return None
    region = region_of(job['location'])
    score += REGION_BONUS[region]
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
                    rows.append({'title': j['title'], 'url': source['base'] + j['externalPath'], 'location': j.get('locationsText', ''), 'description': '', 'source_updated': j.get('postedOn', ''), '_path': j['externalPath']})
                offset += len(postings)
                if offset >= payload['total']:
                    break
                if not postings or offset >= 500:
                    raise ValueError('Incomplete pagination')
        # 「N Locations」看不出城市；对这类职位取详情，拿到全部地点和描述（最多 60 条）
        detail_base = source['url'].rsplit('/jobs', 1)[0]
        seen_paths, fetched = set(), 0
        for row in rows:
            path = row.pop('_path', '')
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            if fetched >= 60 or not re.search(r'\d+ Locations', row['location'] or ''):
                continue
            fetched += 1
            try:
                info = request(detail_base + path).get('jobPostingInfo') or {}
                places = [info.get('location', '')] + list(info.get('additionalLocations') or [])
                row['location'] = '; '.join(x for x in places if x) or row['location']
                row['description'] = plain(info.get('jobDescription', ''))[:3000]
            except Exception:
                pass
        for row in rows:
            row.pop('_path', None)
    elif source['kind'] == 'apple':
        pattern = re.compile(r'<h3><a[^>]+href="([^"]+/details/[^"]+)"[^>]*>(.*?)</a></h3>', re.I | re.S)
        seen = set()
        def apple_page(page):
            separator = '&' if '?' in source['url'] else '?'
            raw = ''
            for _ in range(2):
                try:
                    raw = request_text(f"{source['url']}{separator}page={page}")
                    break
                except Exception:
                    pass
            if not raw:
                return []
            found = list(pattern.finditer(raw))
            page_rows = []
            for index, hit in enumerate(found):
                block = raw[hit.start():found[index + 1].start() if index + 1 < len(found) else hit.start() + 12000]
                location_match = re.search(r'id="search-(?:store-name-container|store-name)-[^"]*"[^>]*>(.*?)</span>', block, re.I | re.S)
                summary_match = re.search(r'job-summary[^>]*>.*?<p[^>]*>\s*<span>(.*?)</span>', block, re.I | re.S)
                href = html.unescape(hit.group(1))
                url = urllib.parse.urljoin(source['url'], href)
                page_rows.append({'title': plain(hit.group(2)), 'url': url,
                                  'location': plain(location_match.group(1)) if location_match else '深圳',
                                  'description': plain(summary_match.group(1)) if summary_match else '',
                                  'source_updated': ''})
            return page_rows
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pages:
            for page_rows in pages.map(apple_page, range(1, 7)):
                for row in page_rows:
                    if row['url'] not in seen:
                        seen.add(row['url'])
                        rows.append(row)
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
        for query in source['queries']:
            if api_key:
                payload = request(source['url'], {'api_key': api_key, 'query': query, 'search_depth': 'advanced', 'max_results': 10, 'include_answer': False})
                results = [(j.get('title', ''), j.get('url', ''), plain(j.get('content', ''))) for j in payload.get('results', [])]
            else:
                raw = request_text('https://html.duckduckgo.com/html/?' + urllib.parse.urlencode({'q': query}))
                results = []
                for href, title in re.findall(r'class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', raw, re.I | re.S):
                    target = urllib.parse.parse_qs(urllib.parse.urlparse(html.unescape(href)).query).get('uddg', [html.unescape(href)])[0]
                    results.append((plain(title), target, ''))
            for title, url, text in results:
                location = '深圳 / 香港' if re.search(r'深圳|Shenzhen|香港|Hong Kong', title + ' ' + text, re.I) else ''
                rows.append({'title': title, 'url': url, 'location': location, 'description': text, 'source_updated': ''})
        if not rows:
            raise ValueError('Boolean search returned no results')
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
    elif source['kind'] == 'tencent':
        import time
        seen = set()
        for query in source['queries']:
            params = urllib.parse.urlencode({'timestamp': int(time.time() * 1000), 'keyword': query, 'pageIndex': 1, 'pageSize': 50, 'language': 'zh-cn', 'area': 'cn'})
            payload = request(source['url'] + '?' + params, headers={'Referer': 'https://careers.tencent.com/'})
            for j in (payload.get('Data') or {}).get('Posts') or []:
                url = (j.get('PostURL') or '').replace('http://', 'https://')
                if not url or url in seen:
                    continue
                seen.add(url)
                rows.append({'title': j.get('RecruitPostName', ''), 'url': url, 'location': j.get('LocationName', ''),
                             'description': plain((j.get('Responsibility') or '') + ' ' + (j.get('Requirement') or '')), 'source_updated': j.get('LastUpdateTime', '')})
    elif source['kind'] == 'feishu':
        host = source['url'].rstrip('/')
        path = source.get('path', 'experienced')
        seen = set()
        for query in source['queries']:
            body = {'keyword': query, 'limit': 50, 'offset': 0, 'job_category_id_list': [], 'tag_id_list': [], 'location_code_list': source.get('location_codes', []),
                    'subject_id_list': [], 'recruitment_id_list': [], 'portal_type': 2, 'job_function_id_list': [], 'portal_entrance': 1}
            qs = urllib.parse.urlencode({'keyword': query, 'limit': 50, 'offset': 0, 'portal_type': 2, 'portal_entrance': 1})
            payload = request(f"{host}/api/v1/search/job/posts?{qs}", body,
                              headers={'portal-platform': '1', 'website-path': path, 'env': 'undefined', 'Accept': 'application/json, text/plain, */*',
                                       'Accept-Language': 'zh-CN,zh;q=0.9', 'Referer': f'{host}/{path}/position?keywords={urllib.parse.quote(query)}', 'Origin': host,
                                       'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36'})
            if payload.get('code') not in (None, 0):
                raise ValueError(f"feishu code={payload.get('code')} {str(payload.get('message', ''))[:80]}")
            for j in (payload.get('data') or {}).get('job_post_list') or []:
                jid = j.get('id')
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                city = (j.get('city_info') or {}).get('name') or (j.get('city_info') or {}).get('en_name') or ''
                rows.append({'title': j.get('title', ''), 'url': f"{host}/{path}/position/{jid}/detail", 'location': city,
                             'description': plain((j.get('description') or '') + ' ' + (j.get('requirement') or ''))[:3000], 'source_updated': str(j.get('publish_time') or '')})
    elif source['kind'] == 'baidu':
        seen = set()
        for query in source['queries']:
            payload = request(source['url'], {'recruitType': 'SOCIAL', 'pageSize': 50, 'keyWord': query, 'curPage': 1, 'projectType': ''}, form=True,
                              headers={'Referer': 'https://talent.baidu.com/jobs/social-list', 'Origin': 'https://talent.baidu.com'})
            records = (payload.get('data') or {}).get('list') or []
            if not records:
                print(f"百度 {query}: 返回键 {list(payload)[:6]} data 键 {list(payload.get('data') or {})[:6] if isinstance(payload.get('data'), dict) else type(payload.get('data')).__name__}")
            for j in records:
                pid = j.get('postId')
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                rows.append({'title': j.get('name', ''), 'url': f"https://talent.baidu.com/jobs/social-detail/{pid}", 'location': j.get('workPlace', ''),
                             'description': plain((j.get('workContent') or '') + ' ' + (j.get('serviceCondition') or ''))[:3000], 'source_updated': str(j.get('publishDate') or '')})
    elif source['kind'] == 'linkedin':
        seen = set()
        for location in source['locations']:
            for query in source['queries']:
                params = urllib.parse.urlencode({'keywords': query, 'location': location, 'start': 0, 'f_TPR': 'r2592000'})
                try:
                    raw = request_text(source['url'] + '?' + params)
                except Exception:
                    continue
                for card in re.findall(r'<li>(.*?)</li>', raw, re.S):
                    href = re.search(r'href="(https://[^"]*?/jobs/view/[^"?]+)', card)
                    title = re.search(r'base-search-card__title[^>]*>(.*?)</h3>', card, re.S)
                    company = re.search(r'base-search-card__subtitle[^>]*>(?:\s*<a[^>]*>)?(.*?)</', card, re.S)
                    place = re.search(r'job-search-card__location[^>]*>(.*?)</span>', card, re.S)
                    if not href or not title or href.group(1) in seen:
                        continue
                    seen.add(href.group(1))
                    rows.append({'title': plain(title.group(1)), 'url': href.group(1), 'location': plain(place.group(1)) if place else location,
                                 'description': '', 'source_updated': '', 'company': plain(company.group(1)) if company else ''})
        if not rows:
            raise ValueError('LinkedIn guest search returned nothing')
    else:
        raise ValueError('Unsupported source kind')
    return [dict(j, company=j.get('company') or source['name'], source=source['id']) for j in rows]


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
                detail = type(exc).__name__
                if isinstance(exc, urllib.error.HTTPError):
                    try:
                        snippet = exc.read(300).decode('utf-8', 'replace').replace('\n', ' ')
                    except Exception:
                        snippet = ''
                    detail = f'HTTP {exc.code} {snippet[:160]}'.strip()
                elif str(exc):
                    detail = f'{detail}: {str(exc)[:160]}'
                print(f"源失败 {source['name']}: {detail}")
                statuses.append({'name': source['name'], 'ok': False, 'error': detail})
                for previous in old.get('jobs', []):
                    if previous['source'] == source['id']:
                        if previous['company'] in config['profile'].get('excluded_companies', []):
                            continue
                        updated = match(dict(previous, description=' '.join(previous.get('reasons', []))), config['profile'])
                        if updated:
                            updated.pop('description', None)
                            jobs[updated['url']] = dict(updated, stale=True)
    # External adapters run after this collector. Keep their last successful rows
    # until the adapter can refresh them, so transient network failures do not
    # empty the page.
    for previous in old.get('jobs', []):
        if previous.get('source') in ('ats-jobs', 'liepin', 'liepin-shenzhen') and previous.get('url') not in jobs:
            refreshed = match(dict(previous, description=' '.join(previous.get('reasons', []))), config['profile'])
            jobs[previous['url']] = dict(previous, stale=True, **({k: refreshed[k] for k in ('region', 'tags', 'score')} if refreshed else {}))
    limited = limit_jobs(jobs.values(), config['profile'])
    return {'updated': now, 'sources': statuses, 'jobs': limited, 'search_links': config.get('search_links', [])}


def render():
    data = json.loads(DATA.read_text()) if DATA.exists() else {}
    esc = html.escape
    parts = [f'<p class="radar-stats">最近尝试更新：{esc(data.get("updated", "尚未运行"))} · 按技术关键词与地点排序，不代表录用概率。</p>']
    parts.append('<p>经验、学历、薪资、签证与远程可工作地区未作匹配，请查看职位原文。「国内其他城市」是深圳、香港以外的中国内地城市；多地点职位请展开原文确认。</p>')
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
    primary = [j for j in data.get('jobs', []) if j.get('listing_type') != 'headhunter']
    headhunters = [j for j in data.get('jobs', []) if j.get('listing_type') == 'headhunter']
    groups = [('深圳 / 香港', [j for j in primary if j['region'] in ('深圳', '香港')]),
              ('国内其他城市', [j for j in primary if j['region'] == '国内']),
              ('远程', [j for j in primary if j['region'] == '远程']),
              ('海外', [j for j in primary if j['region'] == '海外'])]
    for label, group in groups:
        if not group: continue
        parts.append(f'<section data-filter-group><h2>{label} <small>({len(group)})</small></h2><ul class="job-list" data-archive>')
        for job in group:
            search = esc(' '.join([job['title'], job['company'], job['location'], *job['tags']]).lower(), quote=True)
            parts.append(f'<li data-search="{search}" data-tags="{esc("|".join(job["tags"]), quote=True)}"><article><h2><a href="{esc(job["url"], quote=True)}" rel="noopener noreferrer">{esc(job["title"])}</a></h2>')
            parts.append(f'<p>{esc(job["company"])} · {esc(job["location"])} · {esc(job["region"])}</p>')
            parts.append(f'<p>{esc("；".join(job["reasons"]))}</p>')
            state = '待复核：本次来源抓取失败' if job.get('stale') else '最近在招聘列表中发现'
            parts.append(f'<p class="radar-stats">{state} · {esc(job["last_seen"][:10])}</p></article></li>')
        parts.append('</ul></section>')
    if headhunters:
        parts.append(f'<details class="headhunter-jobs" data-filter-group><summary>猎头代招 · 公司未公开 ({len(headhunters)})</summary>')
        parts.append('<p>这些是猎聘匿名代招岗位，可能有价值，但无法核验实际雇主；与企业直招分开显示。</p><ul class="job-list" data-archive>')
        for job in headhunters:
            search = esc(' '.join([job['title'], job['company'], job['location'], *job['tags']]).lower(), quote=True)
            parts.append(f'<li data-search="{search}" data-tags="{esc("|".join(job["tags"]), quote=True)}"><article><h2><a href="{esc(job["url"], quote=True)}" rel="noopener noreferrer">{esc(job["title"])}</a></h2>')
            parts.append(f'<p>猎头代招 · 公司未公开 · {esc(job["location"])} · {esc(job["region"])}</p>')
            parts.append(f'<p>{esc("；".join(job["reasons"]))}</p>')
            parts.append(f'<p class="radar-stats">请先向猎头确认实际公司、职级与薪资 · {esc(job["last_seen"][:10])}</p></article></li>')
        parts.append('</ul></details>')
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
