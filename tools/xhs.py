#!/usr/bin/env python3
"""AI 信息学习卡片：用当天雷达的 high / medium 条目生成「学习要点 + 小红书草稿」，再为前几条做封面图，写入私有 radar-inbox。

流程：
  1. 读 radar/data/<日期>.json，取 high / medium 前 20 条
  2. Gemini（call_llm_json）逐条生成 headline / takeaways / post（结构化 JSON）
  3. 前 XHS_IMAGES（默认 4）条做 3:4 封面图：
       - 配图：Gemini 生图模型画一张无文字的极简插画（GEMINI_IMAGE_MODEL，默认 gemini-2.5-flash-image；
         失败退到 Imagen predict 接口 GEMINI_IMAGEN_MODEL，默认 imagen-4.0-generate-001；再失败就用纯色渐变）
       - 文字：中文标题与要点用 HTML 排版，Playwright 截成 1080×1440 JPEG（生图模型写不好中文，所以文字不交给它）
  4. 写 posts/<日期>.md 与 posts/<日期>/<id>.jpg 到私有仓库；本地留一份 radar/data/xhs-<日期>.md

用法：
  RADAR_DATE=2026-09-19 python3 tools/xhs.py
  python3 tools/xhs.py --list-image-models     # 打印当前 key 能用的生图模型名，确认默认值还对不对
  XHS_IMAGES=0 python3 tools/xhs.py            # 只出文稿不出图
环境：GEMINI_API_KEY（必需）、INBOX_TOKEN / INBOX_REPO（写私有仓库；没有就只写本地）、PW_CHROMIUM（本机 Chromium 路径，可选）。
"""
import base64, html, json, os, re, sys, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar import call_llm_json, log

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'radar/data'
SCHEMA = {'type':'object','properties':{'posts':{'type':'array','items':{'type':'object','properties':{'id':{'type':'string'},'headline':{'type':'string'},'takeaways':{'type':'array','items':{'type':'string'}},'post':{'type':'string'},'image_prompt':{'type':'string'}},'required':['id','headline','takeaways','post','image_prompt'],'additionalProperties':False}}},'required':['posts'],'additionalProperties':False}
SYSTEM = '''你是一个技术型小红书作者，读者是想学习 AI 基础设施、GPU kernel、训练/推理加速、DiT 和端侧部署的工程师。根据输入的新闻条目生成学习卡片和可直接修改发布的小红书草稿。不要编造输入没有的事实，不要夸大结论，不要使用“震惊”“天花板”等标题党。headline 12-24字；takeaways 输出2-4条，每条说明一个可学习的技术点，每条不超过 40 字；post 350-700字，结构为：标题、开头、发生了什么、为什么值得学、我会怎么验证/实践、结尾提问。保留原文链接，文末加“信息来源：URL”。语气清楚、克制、像工程师分享。
image_prompt：给生图模型的英文提示词，描述一张与主题相关的极简扁平插画（几何形状、电路、芯片、数据流、显卡、网络拓扑等意象），暖色调米白背景配赭红点缀，构图居中，明确写 "no text, no letters, no logos"，40 词以内。'''

API = 'https://generativelanguage.googleapis.com/v1beta'


def gh_put(repo, path, data: bytes, token, message):
    url = f'https://api.github.com/repos/{repo}/contents/{path}'
    hdr = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=20) as r: sha = json.load(r).get('sha')
    except urllib.error.HTTPError as e:
        if e.code != 404: raise
        sha = None
    body = {'message': message, 'content': base64.b64encode(data).decode()}
    if sha: body['sha'] = sha
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={**hdr, 'Content-Type': 'application/json'}, method='PUT')
    with urllib.request.urlopen(req, timeout=60): pass


# ---------------------------------------------------------------- 生图
def _gemini_post(path, body, key, timeout=120):
    req = urllib.request.Request(f'{API}/{path}', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'x-goog-api-key': key}, method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.load(r)


def list_image_models(key):
    with urllib.request.urlopen(urllib.request.Request(f'{API}/models?pageSize=200', headers={'x-goog-api-key': key}), timeout=30) as r:
        models = json.load(r).get('models', [])
    for m in models:
        name = m.get('name', '').replace('models/', '')
        if 'image' in name or 'imagen' in name:
            print(f"{name:45s} {','.join(m.get('supportedGenerationMethods', []))}")


def gemini_image(prompt: str, key: str) -> bytes | None:
    """依次试原生生图模型（generateContent 回 inlineData），再试可选的 Imagen predict；都不行返回 None。"""
    models = [m.strip() for m in os.environ.get('GEMINI_IMAGE_MODEL', 'gemini-3.1-flash-image,gemini-2.5-flash-image').split(',') if m.strip()]
    for model in models:
        try:
            r = _gemini_post(f'models/{model}:generateContent', {'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'responseModalities': ['IMAGE', 'TEXT']}}, key)
            for part in (r.get('candidates') or [{}])[0].get('content', {}).get('parts', []):
                if part.get('inlineData', {}).get('data'):
                    log(f'[xhs] 配图：{model}'); return base64.b64decode(part['inlineData']['data'])
            log(f'[xhs] {model} 没有返回图片：{str(r)[:160]}')
        except urllib.error.HTTPError as e:
            log(f'[xhs] {model} HTTP {e.code}：{e.read().decode("utf-8", "replace")[:160]}')
        except Exception as e:
            log(f'[xhs] {model} 失败：{e}')
    imagen = os.environ.get('GEMINI_IMAGEN_MODEL', '').strip()  # 账号没有 Imagen 时留空
    if imagen:
        try:
            r = _gemini_post(f'models/{imagen}:predict', {'instances': [{'prompt': prompt}], 'parameters': {'sampleCount': 1, 'aspectRatio': '1:1'}}, key)
            b64 = (r.get('predictions') or [{}])[0].get('bytesBase64Encoded')
            if b64:
                log(f'[xhs] 配图：{imagen}'); return base64.b64decode(b64)
            log(f'[xhs] {imagen} 没有返回图片：{str(r)[:160]}')
        except urllib.error.HTTPError as e:
            log(f'[xhs] {imagen} HTTP {e.code}：{e.read().decode("utf-8", "replace")[:160]}')
        except Exception as e:
            log(f'[xhs] {imagen} 失败：{e}')
    return None


# ---------------------------------------------------------------- 封面卡片
CARD_CSS = '''
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1440px;background:#fbfaf8;font-family:"Noto Sans CJK SC","Noto Sans SC","PingFang SC","WenQuanYi Zen Hei","Source Han Sans SC",system-ui,sans-serif;color:#1b1b1a}
.card{width:1080px;height:1440px;padding:72px 72px 64px;display:flex;flex-direction:column;gap:36px}
.kicker{display:flex;justify-content:space-between;align-items:center;font-size:26px;color:#78746c;letter-spacing:.04em}
.kicker b{color:#9a3412;font-weight:700}
.art{height:560px;border-radius:28px;overflow:hidden;background:linear-gradient(135deg,#f4f1eb,#fbeee5 60%,#f4f1eb);position:relative;display:flex;align-items:center;justify-content:center}
.art img{width:100%;height:100%;object-fit:cover;display:block}
.art .n{font-size:300px;font-weight:800;color:#9a3412;opacity:.12;letter-spacing:-.04em}
h1{font-size:60px;line-height:1.25;font-weight:800;letter-spacing:-.01em}
ol{list-style:none;display:flex;flex-direction:column;gap:22px}
li{display:flex;gap:20px;font-size:32px;line-height:1.45;color:#3d3e3c}
li i{flex:0 0 46px;height:46px;border-radius:50%;background:#9a3412;color:#fff;font:700 24px/46px sans-serif;text-align:center;font-style:normal;margin-top:2px}
.foot{margin-top:auto;display:flex;justify-content:space-between;align-items:flex-end;font-size:24px;color:#78746c;border-top:2px solid #e6e2d9;padding-top:28px}
.foot b{color:#1b1b1a;font-size:26px}
'''


def card_html(index: int, post: dict, src: dict, date: str, art_b64: str | None) -> str:
    e = html.escape
    art = f'<img src="data:image/png;base64,{art_b64}" alt="">' if art_b64 else f'<div class="n">{index:02d}</div>'
    items = ''.join(f'<li><i>{i}</i><span>{e(t)}</span></li>' for i, t in enumerate(post.get('takeaways', [])[:4], 1))
    domain = re.sub(r'^https?://(www\.)?', '', src.get('link', '')).split('/')[0]
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>{CARD_CSS}</style></head><body><div class="card">
<div class="kicker"><span><b>Anaxagore</b> · AI 信息学习卡片</span><span>{e(date)} · {index:02d}</span></div>
<div class="art">{art}</div>
<h1>{e(post.get('headline', ''))}</h1>
<ol>{items}</ol>
<div class="foot"><span>来源 · {e(domain)}</span><b>lgystoic.github.io/radar/{e(date)}/</b></div>
</div></body></html>'''


def render_cards(jobs: list[tuple[str, str]], out_dir: Path) -> list[Path]:
    """jobs = [(id, html)] → JPEG 文件；Playwright 不可用时返回空列表。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log('[xhs] 未安装 playwright，跳过封面图'); return []
    import glob
    exe = os.environ.get('PW_CHROMIUM') or next(iter(sorted(glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome'))), None)
    out_dir.mkdir(parents=True, exist_ok=True); files = []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=exe, args=['--no-sandbox']) if exe else p.chromium.launch(args=['--no-sandbox'])
            for pid, doc in jobs:
                pg = b.new_page(viewport={'width': 1080, 'height': 1440}, device_scale_factor=1)
                pg.set_content(doc); pg.wait_for_timeout(150)
                f = out_dir / f'{pid}.jpg'; pg.screenshot(path=str(f), type='jpeg', quality=86); pg.close(); files.append(f)
            b.close()
    except Exception as e:  # 浏览器问题不拖垮文稿
        log(f'[xhs] 渲染封面失败：{e}')
    return files


def main():
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if '--list-image-models' in sys.argv:
        if not key: raise SystemExit('需要 GEMINI_API_KEY')
        list_image_models(key); return
    date = os.environ.get('RADAR_DATE') or datetime.now().strftime('%Y-%m-%d')
    src = DATA / f'{date}.json'
    if not src.exists(): raise SystemExit(f'没有 {src}')
    data = json.loads(src.read_text())
    items = [x for x in data.get('items', []) if x.get('priority') in ('high', 'medium')][:20]
    if not items: log('[xhs] 没有 high/medium 条目'); return
    prompt = '以下是今日条目 JSON，请逐条生成：\n' + json.dumps([{'id': x.get('id'), 'title': x.get('title'), 'summary': x.get('summary'), 'why': x.get('why'), 'link': x.get('link'), 'tags': x.get('tags', [])} for x in items], ensure_ascii=False)
    result = call_llm_json(SYSTEM, prompt, SCHEMA, label='xhs')
    if not result: raise SystemExit('Gemini 未返回文稿')
    byid = {x['id']: x for x in items}
    posts = [p for p in result.get('posts', []) if p.get('id') in byid]

    # 封面图：前 N 条
    n_images = int(os.environ.get('XHS_IMAGES', '4'))
    jobs, art_used = [], 0
    for i, post in enumerate(posts[:n_images], 1):
        art = gemini_image(post.get('image_prompt') or f"minimal flat illustration about {post.get('headline','AI infrastructure')}, warm off-white background, rust accent, no text, no letters, no logos", key) if key and n_images else None
        if art: art_used += 1
        jobs.append((post['id'], card_html(i, post, byid[post['id']], date, base64.b64encode(art).decode() if art else None)))
    out_dir = DATA / 'xhs' / date
    files = render_cards(jobs, out_dir) if jobs else []
    log(f'[xhs] 封面图 {len(files)} 张（其中 {art_used} 张带生图配图）')

    lines = [f'# AI 信息学习卡片 · {date}', '', '> 自动生成初稿，请人工核对事实和语气后再发布。封面图 3:4，可直接作为小红书首图；配图由生图模型生成，仅作装饰。', '']
    have_img = {f.stem for f in files}
    for post in posts:
        s = byid[post['id']]
        lines += [f'## {post.get("headline", "")}', '']
        if post['id'] in have_img: lines += [f'![封面](./{date}/{post["id"]}.jpg)', '']
        lines += [f'原始条目：{s.get("title", "")}', f'链接：{s.get("link", "")}', '', '**学习要点**']
        lines += [f'- {x}' for x in post.get('takeaways', [])]
        lines += ['', '**小红书草稿**', '', post.get('post', ''), '', '---', '']
    content = '\n'.join(lines)
    (DATA / f'xhs-{date}.md').write_text(content, encoding='utf-8')
    token, repo = os.environ.get('INBOX_TOKEN', '').strip(), os.environ.get('INBOX_REPO', 'lgyStoic/radar-inbox')
    if token:
        for f in files:
            gh_put(repo, f'posts/{date}/{f.name}', f.read_bytes(), token, f'AI learning cover: {date} {f.stem}')
        gh_put(repo, f'posts/{date}.md', content.encode('utf-8'), token, f'AI learning posts: {date}')
    log(f'[xhs] 生成 {len(posts)} 条文稿、{len(files)} 张封面，写入 {repo if token else DATA}')


if __name__ == '__main__':
    main()
