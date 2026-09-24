#!/usr/bin/env python3
"""小红书文稿生成：两种内容，都写入私有 radar-inbox 的 posts/。

  cards（每天）：当天雷达 high / medium 前 20 条 → 每条 标题 / 正文 / 标签 + 3:4 封面卡片（前 XHS_IMAGES 条带生图配图）
                 → posts/cards/<日期>.md、posts/cards/<日期>/<id>.jpg
  jobs（每周一）：radar/data/jobs.json 里有真实公司名、未过期的岗位，按分数挑 12 条 → 一篇「岗位精选」+ 1 张封面
  tracks（每天，有料才发）：radar/data/tracks/<id>.json 自上一期以来的新条目 → 模型先判 worth → 值得才出「专题日报」+ 1 张封面
                 → posts/tracks/<id>/<日期>.md、posts/tracks/<id>/<日期>/cover.jpg
                 → posts/jobs/<日期>.md、posts/jobs/<日期>/cover.jpg
  每次运行后重写 posts/README.md（两类最近 30 期的索引）。本地各留一份 radar/data/xhs-*.md（已 gitignore）。

封面：文字用 HTML 排版、Playwright 截图，使用本地渐变设计，不依赖生图 API。

用法：
  RADAR_DATE=2026-09-19 python3 tools/xhs.py            # cards
  python3 tools/xhs.py --jobs                            # jobs；XHS_JOBS_REGION=cn|overseas 只挑国内/海外远程
  python3 tools/xhs.py --check-llm                       # 检查 LongCat 文本模型连通性
  XHS_IMAGES=0 python3 tools/xhs.py                      # cards 只出文稿不出图
环境：LONGCAT_API_KEY（必需，文稿生成）、INBOX_TOKEN / INBOX_REPO（写私有仓库；没有就只写本地）、PW_CHROMIUM、XHS_PREVIEW=1（第 1 条打日志）。
"""
import base64, html, json, os, re, sys, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar import call_llm_json, log, load_tracks

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'radar/data'
SCHEMA = {'type':'object','properties':{'posts':{'type':'array','items':{'type':'object','properties':{'id':{'type':'string'},'headline':{'type':'string'},'takeaways':{'type':'array','items':{'type':'string'}},'title':{'type':'string'},'body':{'type':'string'},'tags':{'type':'array','items':{'type':'string'}},'image_prompt':{'type':'string'},'entity':{'type':'string'},'novelty':{'type':'string','enum':['new','update','same']},'followup_of':{'type':'string'}},'required':['id','headline','takeaways','title','body','tags','image_prompt','entity','novelty','followup_of'],'additionalProperties':False}}},'required':['posts'],'additionalProperties':False}
SYSTEM = '''你是一个在小红书分享 AI infra 学习笔记的工程师。读者是想学 AI 基础设施、GPU kernel、训练/推理加速、DiT、端侧部署的同行。根据输入的新闻条目，逐条产出可以直接复制粘贴发布的小红书笔记。不要编造输入没有的事实，不要夸大，不要用“震惊”“天花板”“炸裂”这类词。

每条输出字段：
- headline：学习卡片标题，12–24 字，用于封面图。
- takeaways：2–4 条可学习的技术点，每条 ≤40 字，用于封面图。
- title：小红书标题，≤20 字（小红书硬限制），有具体信息量，可用一个 emoji 开头。
- body：小红书正文，直接发布用，300–600 字。硬性要求：
  1. 不要出现任何小节标签（禁止写“标题：”“开头：”“发生了什么：”“为什么值得学：”“结尾：”之类）。
  2. 短段落，每段 1–3 句，段落之间空一行；可以用 1–3 个 emoji 做段首符号，不要多。
  3. 第一句要能让人停下来（一个具体的数字、变化或反常识点），不要“各位同学”“大家好”这类开场。
  4. 内容顺序自然衔接：发生了什么 → 为什么对做 infra 的人重要 → 学到的具体技术点（可分行列出）→ 一句自己的看法或接下来想试的方向 → 一个开放式提问 → 最后一段是关注引导（见第 9 条）。
  5. 用第一人称、口语化但准确，像发给同行的笔记，不像新闻稿。
  9. 关注引导：正文最后单独一段，1–2 句，把「关注」和这个账号的固定价值绑定——我每天从几十条 AI infra 新闻里挑出值得学的做成一张学习卡片。要自然、具体、不卑微，每条措辞都不一样，参考风格（不要照抄）：
     - 「这类推理系统的更新我每天会挑一条拆开讲，想跟着补 infra 知识的可以关注一下，明天见。」
     - 「每天一张 AI infra 学习卡片，先收藏，等你真要上手时回来翻。」
     - 「如果你也在做训练/推理加速，关注我，这个系列每天更新，评论区一起把细节聊透。」
     - 「觉得有用的话收藏 + 关注，下一张卡片讲 <与本条相关的方向>。」（只在你确实能从输入其他条目推断出方向时使用）
     - 「这是第 N 天了，前面的都在主页合集里，想系统补 infra 的直接翻。」（输入里给了期数时可用）
     禁止：「求关注」「点赞关注走一波」「关注不迷路」这类模板话；不要承诺抽奖、资料包。
  8. 技术点只能来自输入条目的 title / summary / why，输入没写的细节（性能数字、实现方式、显存/吞吐变化）一律不补；不要虚构自己的团队、项目、经历，「接下来想试」只能写成个人打算，不要写“我们的流程里”。
  6. 不要放任何 URL（小红书会限流），需要提来源就写名称，如“来源：SGLang 官方 release notes”。
  7. 正文末尾不要放话题标签，标签单独放 tags。
- tags：3–5 个小红书话题词，不带 #。第一个固定为 "AIInfra学习卡片"（系列聚合词，每条都要），其余按内容选，如 "大模型推理"、"CUDA"、"SGLang"。
- image_prompt：给生图模型的英文提示词，描述一张与主题相关的极简扁平插画（几何形状、电路、芯片、数据流、显卡、网络拓扑等意象），暖色调米白背景配赭红点缀，构图居中，明确写 "no text, no letters, no logos"，40 词以内。
- entity：这条的主体，规范短名（模型 / 产品 / 项目名带版本，如 "DeepSeek-V4.1-Flash"、"SGLang v0.5.20"、"Qwen3.8"），同一主体必须写成完全一样的字符串。
- novelty 与 followup_of：用户消息里会给「近 7 天已写过的主题」列表。这条如果和列表里某个主题是同一件事（换个来源再报）→ novelty = "same"，followup_of 填那个主题；如果是同一主体的新进展（论文之后出权重、发版之后被框架支持、有了 benchmark）→ "update"，followup_of 填那个主题，正文第一段必须承接：「上次说了 X，这次 Y」；否则 "new"，followup_of 留空。'''
JOBS_SCHEMA = {'type':'object','properties':{'headline':{'type':'string'},'highlights':{'type':'array','items':{'type':'string'}},'title':{'type':'string'},'body':{'type':'string'},'tags':{'type':'array','items':{'type':'string'}},'image_prompt':{'type':'string'}},'required':['headline','highlights','title','body','tags','image_prompt'],'additionalProperties':False}
JOBS_SYSTEM = '''你是一个在小红书做「AI infra 岗位精选」周报的工程师，不是 HR，也没有内推渠道。输入是一组从各公司官方招聘页和猎聘公开页面抓到的岗位（公司、岗位名、地点、方向标签、匹配理由、来源）。产出一篇可直接发布的小红书笔记。

硬性要求：
1. 只能用输入里有的信息：不要编造薪资、年限、团队规模、面试流程；输入没有薪资就一个字都不提薪资。公司名做规范化：去掉「招聘」后缀（腾讯招聘 → 腾讯），域名写成公司名（cerebras.ai → Cerebras）。
2. 不要说「内推」「帮投」「私信我」「留邮箱」；来源统一写「各公司官方招聘页和猎聘公开信息」。
3. title ≤20 字，带数量和范围，如「本周 12 个 AI infra 岗位｜深圳 5 个」。
4. body 350–650 字：第一段一句话说这周岗位的整体观察（哪个方向/城市在放岗，只能从输入归纳）；然后逐条列岗位，每条一行：「公司｜岗位｜地点」，后面跟一句 ≤25 字的「为什么值得看」（依据 tags / reasons）；不要出现任何 URL；不要小节标签；短段落空行分隔；最后一段是关注引导：说明这是每周一更新的系列，完整岗位列表在主页站点每天更新，收藏 + 关注，措辞自然，不要「求关注」「关注不迷路」。
5. headline：封面标题 12–20 字。highlights：封面用 4–6 行，每行 ≤22 字，格式「公司 · 地点 · 方向」，挑最有辨识度的公司。
6. tags：3–5 个话题词，不带 #，第一个固定 "AIInfra岗位"，其余如 "AI Infra"、"大模型推理"、"深圳求职"、"CUDA"。
7. image_prompt：英文，极简扁平插画，与「招聘/机会/城市与芯片」相关的意象，暖色米白背景赭红点缀，"no text, no letters, no logos"，40 词以内。'''
JOBS_TAG = 'AIInfra岗位'

TRACK_SYSTEM = '''你在小红书做「{name}日报」，读者是做生成模型与推理加速的工程师。输入是这个专题自上一期以来的新条目（标题、摘要、主体、类型、来源），以及站内周综述和现状表（只作背景，不要把里面的旧内容当成新进展）。先判断值不值得发，再写稿。

先判 worth：只有出现了「真正的进展」才值得发——新模型 / 权重 / 版本发布、有具体结论的论文或评测、推理框架对新模型的支持、可复现的工程结果。全是泛新闻、融资、观点、转述、社区微调或量化版 → worth = false，worth_reason 一句话说明，其余字段随意填短内容即可。

worth = true 时的硬性要求：
1. 只用输入里的事实，不补充你记忆里的模型、参数、日期；没有的信息就不写。
2. title ≤20 字，点明今天最大的一件事，如「Wan2.6 开源｜今日视频模型 3 件事」。
3. body 250–550 字：第一段一句话说今天的重点 → 逐条列 2–6 件进展（数量随实际，宁少勿凑），每条一行「主体｜一句进展」，后面跟一句 ≤25 字的「意味着什么」→ 一句自己的判断（哪条最值得跟）→ 一个提问 → 最后一段关注引导：说明这是{name}日报，有料才发、不凑数，完整时间线和现状表在主页站点的专题页，收藏 + 关注，措辞自然，不要「求关注」「关注不迷路」。不放 URL，不要小节标签，短段落空行分隔。
4. headline：封面标题 12–20 字。highlights：封面用 2–6 行，每行 ≤22 字，「主体 · 一句进展」。
5. tags：3–5 个话题词，不带 #，第一个固定 "{tag}"，其余如 "AI Infra"、"视频生成"、"世界模型"、"DiT"。
6. image_prompt：英文，极简扁平插画，与专题意象相关（胶片帧、时间轴、三维网格、粒子世界等），暖色米白背景赭红点缀，"no text, no letters, no logos"，40 词以内。'''
TRACK_SCHEMA = {'type':'object','properties':{**JOBS_SCHEMA['properties'], 'worth':{'type':'boolean'}, 'worth_reason':{'type':'string'}}, 'required': JOBS_SCHEMA['required'] + ['worth', 'worth_reason'], 'additionalProperties': False}
TRACK_TAG = {'video': '视频模型日报', 'world': '世界模型日报'}

RANK_SCHEMA = {'type':'object','properties':{'ranking':{'type':'array','items':{'type':'object','properties':{'id':{'type':'string'},'audience':{'type':'integer'},'hook':{'type':'integer'},'discuss':{'type':'integer'},'save':{'type':'integer'},'reason':{'type':'string'}},'required':['id','audience','hook','discuss','save','reason'],'additionalProperties':False}}},'required':['ranking'],'additionalProperties':False}
RANK_SYSTEM = '''你是小红书 AI 技术类账号的运营编辑。输入是同一天生成的一批笔记（标题 + 正文前 200 字 + 原始新闻标题），请判断在小红书上哪些更可能被 AI 从业者点开、点赞、收藏、评论。逐条给 4 个维度 1–5 分（整数）和一句 ≤30 字理由；同一批内要拉开差距，不要都给 3–4 分：
- audience 受众广度：多少 AI 从业者会关心（大厂/明星模型发布 5，通用推理/训练技巧 4，特定框架细节 3，冷门硬件或论文 1–2）
- hook 钩子强度：标题和第一句有没有具体数字、对比、反常识点
- discuss 可讨论性：能不能引发站队、经验交流、提问（如 vLLM vs SGLang、值不值得升级）
- save 收藏价值：是不是查阅型内容（清单、步骤、参数、对照表）
只输出评分，不改写内容。'''
BRAND_RE = re.compile(r'DeepSeek|Qwen|通义|OpenAI|GPT|NVIDIA|英伟达|Anthropic|Claude|Gemini|Google|Llama|Meta|Kimi|月之暗面|MiniMax|智谱|GLM|Mistral|vLLM|SGLang|PyTorch|CUDA|H100|H200|B200|Blackwell|Hopper|Jetson|昇腾|华为|Huawei|字节|豆包|Seed|Grok|xAI|Apple|苹果', re.I)
CAT_HEAT = {'release': 1.0, 'trend': 0.8, 'infra': 0.7, 'people': 0.6, 'research': 0.5, 'industry': 0.4}


def objective_heat(src: dict, post: dict) -> float:
    """0–1：雷达优先级、类别、标题里有没有大厂/明星模型名、有没有具体数字。不依赖模型。"""
    h = {'high': 1.0, 'medium': 0.6}.get(src.get('priority'), 0.3) * 0.4
    h += CAT_HEAT.get(src.get('category'), 0.5) * 0.3
    text = f"{post.get('headline', '')} {post.get('title', '')} {src.get('title', '')}"
    h += 0.2 if BRAND_RE.search(text) else 0
    h += 0.1 if re.search(r'\d', post.get('title', '') + post.get('headline', '')) else 0
    h += 0.1 if src.get('tracks') else 0  # 专题条目：账号定位就是这两条线
    return round(min(h, 1.0), 3)


def rank_posts(posts: list[dict], byid: dict) -> list[dict]:
    """最终分 = 0.5 量表（模型 4 维相对打分）+ 0.3 客观热度 + 0.2 雷达优先级；模型失败时只用后两项。"""
    if not posts: return posts
    prompt = '以下是今天的笔记，请逐条评分：\n' + json.dumps([{'id': p['id'], 'title': p.get('title'), 'headline': p.get('headline'), 'body_head': (p.get('body') or '')[:200], 'news_title': byid[p['id']].get('title'), 'category': byid[p['id']].get('category')} for p in posts], ensure_ascii=False)
    result = call_llm_json(RANK_SYSTEM, prompt, RANK_SCHEMA, label='xhs-rank') or {}
    rubric = {r['id']: r for r in result.get('ranking', []) if r.get('id')}
    for p in posts:
        src = byid[p['id']]; r = rubric.get(p['id'])
        heat = objective_heat(src, p)
        radar = {'high': 1.0, 'medium': 0.6}.get(src.get('priority'), 0.3)
        if r:
            dims = {k: max(1, min(5, int(r.get(k, 3)))) for k in ('audience', 'hook', 'discuss', 'save')}
            rub = (sum(dims.values()) - 4) / 16  # 4–20 → 0–1
            p['rank'] = {'score': round(0.5 * rub + 0.3 * heat + 0.2 * radar, 3), **dims, 'heat': heat, 'reason': r.get('reason', '')[:40]}
        else:
            p['rank'] = {'score': round(0.6 * heat + 0.4 * radar, 3), 'heat': heat, 'reason': '模型未评分，按客观热度'}
    for p in posts:
        if p.get('rank_penalty'): p['rank']['score'] = round(p['rank']['score'] - p['rank_penalty'], 3)
    posts.sort(key=lambda p: -p['rank']['score'])
    if not rubric: log('[xhs] 排序：模型未返回评分，只按客观热度 + 雷达优先级')
    return posts


TITLE_SCHEMA = {'type':'object','properties':{'titles':{'type':'array','items':{'type':'object','properties':{'id':{'type':'string'},'title':{'type':'string'}},'required':['id','title'],'additionalProperties':False}}},'required':['titles'],'additionalProperties':False}


def shorten_titles(posts: list[dict], limit: int = 20) -> None:
    """小红书标题上限 20 字（中英文数字每个算 1 字）。超长的攒一批让模型改到 ≤18 字，保留信息量，emoji 最多 1 个。"""
    long_ = [p for p in posts if len(p.get('title', '')) > limit]
    if not long_: return
    prompt = json.dumps([{'id': p['id'], 'title': p['title'], 'headline': p.get('headline', '')} for p in long_], ensure_ascii=False)
    r = call_llm_json('把下面每条小红书标题改写到 18 个字符以内（中文、英文字母、数字、标点、emoji 每个都算 1 个字符）。保留最有信息量的名词和数字，去掉修饰词；emoji 最多保留 1 个放开头；不要标题党；不改事实。', prompt, TITLE_SCHEMA, label='xhs-title') or {}
    new = {t['id']: t['title'].strip() for t in r.get('titles', []) if t.get('id')}
    for p in long_:
        t = new.get(p['id'])
        if t and len(t) <= limit: p['title'] = t
        else: log(f'[xhs] 标题仍超 {limit} 字，发布前请手改：{p["title"]}')
    log(f'[xhs] 改短标题 {sum(1 for p in long_ if len(p["title"]) <= limit)}/{len(long_)} 条')


def gh_get_text(repo, path, token) -> str:
    d = gh_get_json(repo, path, token)
    if isinstance(d, dict) and d.get('content'):
        return base64.b64decode(d['content']).decode('utf-8', 'replace')
    return ''


def load_topic_history(repo: str, token: str, date: str, days: int = 7) -> tuple[list[dict], dict]:
    """(近 N 天已写过的主题列表, 原始 topics.json)。已发布 = stats.md 里出现过的序号。"""
    if not token: return [], {}
    from datetime import timedelta
    try:
        topics = json.loads(gh_get_text(repo, 'posts/topics.json', token) or '{}')
    except json.JSONDecodeError:
        topics = {}
    posted = set(re.findall(r'\b(cards/\d{4}-\d{2}-\d{2}#\d{2})\b', gh_get_text(repo, 'posts/stats.md', token) or ''))
    cutoff = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=days)).strftime('%Y-%m-%d')
    hist = []
    for d, rows in sorted(topics.items(), reverse=True):
        if d < cutoff or d >= date: continue
        for r in rows:
            if r.get('entity'):
                hist.append({'date': d, 'entity': r['entity'], 'title': r.get('title', ''), 'posted': f"cards/{d}#{r.get('seq', 0):02d}" in posted})
    return hist, topics


def apply_novelty(posts: list[dict], hist: list[dict]) -> list[dict]:
    """same 且已发 → 丢；same 未发 → 降权并标注；update → 标注承接。"""
    posted_entities = {h['entity'] for h in hist if h['posted']}
    seen_dates = {}
    for h in hist: seen_dates.setdefault(h['entity'], h['date'])
    kept = []
    for p in posts:
        nov, ref = p.get('novelty', 'new'), (p.get('followup_of') or '').strip()
        if nov == 'same' and ref and ref in posted_entities:
            log(f"[xhs] 丢弃重复选题（{ref} 已于 {seen_dates.get(ref)} 发过）：{p.get('title', '')}")
            continue
        if nov == 'same' and ref:
            p['note'] = f'同主题 {seen_dates.get(ref, "")} 已生成过（未发），重复选题'
            p['rank_penalty'] = 0.15
        elif nov == 'update' and ref:
            p['note'] = f'承接 {seen_dates.get(ref, "")} 的「{ref}」'
        kept.append(p)
    return kept


def dedupe_same_day(posts: list[dict]) -> list[dict]:
    """同一天同一主体出现多条（热榜条目 + 论文 + 新闻）：只留排序最高的一条当主稿，其余降权并标注，md 里仍保留供合并素材。"""
    first: dict[str, int] = {}
    for i, p in enumerate(posts, 1):
        ent = (p.get('entity') or '').strip().lower()
        if not ent: continue
        if ent in first:
            p['note'] = (p.get('note') + '；' if p.get('note') else '') + f'与第 {first[ent]:02d} 条同主体，素材可合并'
            if 'rank' in p: p['rank']['score'] = round(p['rank']['score'] - 0.2, 3)
        else:
            first[ent] = i
    posts.sort(key=lambda p: -p.get('rank', {}).get('score', 0))
    return posts


def save_topics(repo: str, token: str, topics: dict, date: str, posts: list[dict]):
    if not token: return
    topics[date] = [{'seq': i, 'id': p['id'], 'entity': p.get('entity', ''), 'title': p.get('title', ''), 'novelty': p.get('novelty', 'new')} for i, p in enumerate(posts, 1)]
    from datetime import timedelta
    cutoff = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=45)).strftime('%Y-%m-%d')
    topics = {d: v for d, v in topics.items() if d >= cutoff}
    try:
        gh_put(repo, 'posts/topics.json', json.dumps(topics, ensure_ascii=False, indent=1).encode('utf-8'), token, f'topics: {date}')
    except Exception as e:
        log(f'[xhs] topics.json 写入失败：{e}')


def episode_number(repo: str, token: str, kind: str, date: str) -> int | None:
    """第几期 = 私有仓库该目录下 md 数（含今天）。没有 token 返回 None。"""
    if not token: return None
    try:
        names = {e['name'][:-3] for e in gh_get_json(repo, f'posts/{kind}', token) if isinstance(e, dict) and e.get('name', '').endswith('.md')}
        names.add(date)
        return len(names)
    except Exception as e:
        log(f'[xhs] 期数查询失败：{e}'); return None
ANON_RE = re.compile(r'^某|知名|保密|不便公开|匿名')

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



def gh_get_json(repo, path, token):
    url = f'https://api.github.com/repos/{repo}/contents/{path}'
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}), timeout=20) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404: return []
        raise


def update_index(repo, token):
    """重写 posts/README.md：两类内容各列最近 30 期。"""
    sections = [('cards', '每日学习卡片', '标题 / 正文 / 标签复制即发，封面在同名目录'), ('jobs', 'AI infra 岗位精选（每周一）', '一篇文稿 + 封面；岗位明细表附在文末供核对')]
    sections += [(f'tracks/{t["id"]}', f'{t["name"]}日报（每天，有料才发）', '一篇文稿 + 封面；条目明细附在文末供核对') for t in load_tracks() if t.get('post')]
    lines = ['# 小红书文稿', '', '自动生成初稿，发布前核对事实。目录：`cards/` 每日学习卡片，`jobs/` 岗位周报，`tracks/<id>/` 专题日报（有料才发）；`<日期>.md` 是文稿，`<日期>/` 是封面图。', '']
    for d, title, note in sections:
        entries = gh_get_json(repo, f'posts/{d}', token)
        mds = sorted((e['name'][:-3] for e in entries if isinstance(e, dict) and e.get('name', '').endswith('.md')), reverse=True)[:30]
        lines += [f'## {title}', '', note, '']
        lines += [f'- [{m}]({d}/{m}.md)' for m in mds] or ['- （暂无）']
        lines.append('')
    gh_put(repo, 'posts/README.md', '\n'.join(lines).encode('utf-8'), token, 'posts index')

SERIES_TAG = 'AIInfra学习卡片'
LABEL_RE = re.compile(r'^[ \t\*#]*(标题|开头|发生了什么|为什么值得学|我会怎么验证/实践|我会怎么验证|实践|结尾提问|结尾|信息来源)\s*[:：]\s*\**\s*', re.M)
URL_RE = re.compile(r'https?://\S+')


def clean_post(p: dict) -> dict:
    """模型偶尔把结构提示当成小节标签写进正文；发布前统一清掉，URL 一律去掉（小红书限流站外链接）。"""
    body = p.get('body', '')
    body = LABEL_RE.sub('', body)
    body = URL_RE.sub('', body)
    body = re.sub(r'\n{3,}', '\n\n', body).strip()
    body = body.replace('关注不迷路', '关注我')  # 模型偶尔无视禁令，兜底替换
    body = re.sub(r'(点赞)?关注走一波[！!。]?', '关注我', body)
    p['body'] = body
    title = re.sub(r'\s+', ' ', URL_RE.sub('', LABEL_RE.sub('', p.get('title', '')))).strip()
    if len(title) > 20:
        title = re.sub(r'(?<=[^\x00-\x7f])\s+|\s+(?=[^\x00-\x7f])', '', title)  # 只去中文旁的空格，英文词间保留
    p['title'] = title
    tags = [re.sub(r'[\s#]+', '', t) for t in p.get('tags', []) if re.sub(r'[\s#]+', '', t)]
    tags = [SERIES_TAG] + [t for t in tags if t != SERIES_TAG]
    p['tags'] = tags[:5]
    return p


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
.jobs .art,.track .art{height:420px}
.jobs li,.track li{font-size:29px;line-height:1.4}
.jobs ol,.track ol{gap:16px}
.foot{margin-top:auto;display:flex;justify-content:space-between;align-items:flex-end;font-size:24px;line-height:1.5;color:#78746c;border-top:2px solid #e6e2d9;padding-top:28px}
.foot b{color:#1b1b1a;font-size:26px}
'''


def card_html(index: int, post: dict, src: dict, date: str, art_b64: str | None, *, kind: str = 'cards', episode: int | None = None) -> str:
    e = html.escape
    art = f'<img src="data:image/png;base64,{art_b64}" alt="">' if art_b64 else f'<div class="n">{index:02d}</div>'
    rows = post.get('takeaways') or post.get('highlights') or []
    rows = rows[:6 if kind in ('jobs', 'track') else 4]
    items = ''.join(f'<li><i>{i}</i><span>{e(t)}</span></li>' for i, t in enumerate(rows, 1))
    if kind == 'jobs':
        kicker, right = 'AI infra 岗位精选 · 每周一' + (f' · 第 {episode} 期' if episode else ''), f'{e(date)} · {len(src.get("jobs", []))} 个岗位'
        foot_l, foot_r = '来源 · 各公司官方招聘页 / 猎聘公开信息<br>完整列表每天更新 · 收藏 + 关注', 'lgystoic.github.io/radar/jobs/'
    elif kind == 'track':
        kicker, right = f'{e(src.get("track_name", ""))}日报 · 有料才发' + (f' · 第 {episode} 期' if episode else ''), f'{e(date)} · {src.get("n", 0)} 条进展'
        foot_l, foot_r = '来源 · 论文 / 官方发布 / HF · 专题页有完整时间线与现状表<br>有进展就更新 · 收藏 + 关注', f'lgystoic.github.io/radar/tracks/{e(src.get("track_id", ""))}/'
    else:
        domain = re.sub(r'^https?://(www\.)?', '', src.get('link', '')).split('/')[0]
        kicker, right = 'AI 信息学习卡片 · 每天一张' + (f' · 第 {episode} 天' if episode else ''), f'{e(date)} · {index:02d}'
        foot_l, foot_r = f'来源 · {e(domain)}<br>关注看每日更新 · 收藏回头翻', f'lgystoic.github.io/radar/{e(date)}/'
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>{CARD_CSS}</style></head><body><div class="card {kind}">
<div class="kicker"><span><b>Anaxagore</b> · {kicker}</span><span>{right}</span></div>
<div class="art">{art}</div>
<h1>{e(post.get('headline', ''))}</h1>
<ol>{items}</ol>
<div class="foot"><span>{foot_l}</span><b>{foot_r}</b></div>
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


def out_paths(kind: str, date: str):
    """(本地 md, 本地图目录, 私有仓库 md, 私有仓库图目录)"""
    return DATA / f"xhs-{kind.replace('/', '-')}-{date}.md", DATA / 'xhs' / kind / date, f'posts/{kind}/{date}.md', f'posts/{kind}/{date}'


def publish(kind: str, date: str, content: str, files: list[Path]):
    md_local, _, md_remote, img_remote = out_paths(kind, date)
    md_local.write_text(content, encoding='utf-8')
    token, repo = os.environ.get('INBOX_TOKEN', '').strip(), os.environ.get('INBOX_REPO', 'lgyStoic/radar-inbox')
    if token:
        for f in files:
            gh_put(repo, f'{img_remote}/{f.name}', f.read_bytes(), token, f'xhs {kind} cover: {date} {f.stem}')
        gh_put(repo, md_remote, content.encode('utf-8'), token, f'xhs {kind}: {date}')
        try: update_index(repo, token)
        except Exception as e: log(f'[xhs] 索引更新失败：{e}')
    return repo if token else md_local


def run_cards(date: str):
    src = DATA / f'{date}.json'
    if not src.exists(): raise SystemExit(f'没有 {src}')
    data = json.loads(src.read_text())
    items = [x for x in data.get('items', []) if x.get('priority') in ('high', 'medium')][:20]
    if not items: log('[xhs] 没有 high/medium 条目'); return
    token, repo = os.environ.get('INBOX_TOKEN', '').strip(), os.environ.get('INBOX_REPO', 'lgyStoic/radar-inbox')
    hist, topics = load_topic_history(repo, token, date)
    hist_txt = ('\n\n近 7 天已写过的主题（entity｜日期｜是否已发布｜标题）：\n' + '\n'.join(f"{h['entity']}｜{h['date']}｜{'已发' if h['posted'] else '未发'}｜{h['title'][:40]}" for h in hist[:60])) if hist else '\n\n近 7 天没有已写过的主题，novelty 全部填 new。'
    prompt = '以下是今日条目 JSON，请逐条生成：\n' + json.dumps([{'id': x.get('id'), 'title': x.get('title'), 'summary': x.get('summary'), 'why': x.get('why'), 'link': x.get('link'), 'tags': x.get('tags', [])} for x in items], ensure_ascii=False) + hist_txt
    result = call_llm_json(SYSTEM, prompt, SCHEMA, label='xhs')
    if not result: raise SystemExit('文本模型未返回文稿')
    byid = {x['id']: x for x in items}
    posts = [clean_post(p) for p in result.get('posts', []) if p.get('id') in byid]
    posts = apply_novelty(posts, hist)
    shorten_titles(posts)
    posts = rank_posts(posts, byid)  # 按小红书发布价值排序，前几条就是今天该发的
    posts = dedupe_same_day(posts)
    episode = episode_number(repo, token, 'cards', date)

    n_images = int(os.environ.get('XHS_IMAGES', '4'))
    jobs = []
    for i, post in enumerate(posts[:n_images], 1):
        jobs.append((post['id'], card_html(i, post, byid[post['id']], date, None, episode=episode)))
    _, img_dir, _, _ = out_paths('cards', date)
    files = render_cards(jobs, img_dir) if jobs else []
    log(f'[xhs] 封面图 {len(files)} 张（本地渐变设计）')

    preview = os.environ.get('XHS_PREVIEW') == '1'
    lines = [f'# AI 信息学习卡片 · {date}' + (f' · 第 {episode} 天' if episode else ''), '', '> 自动生成初稿，请人工核对事实和语气后再发布。**已按小红书发布价值排序**：前 3 条标「今日必发」，封面图给前几条。每条：封面 → 标题 → 正文 → 话题标签，复制即发；原文链接单独列出，是否放评论区自己定。', '', '## 今日发布顺序', '', '| 序 | 标题 | 主体 | 总分 | 受众 | 钩子 | 讨论 | 收藏 | 热度 | 理由 |', '|---|---|---|---|---|---|---|---|---|---|']
    for i, post in enumerate(posts, 1):
        r = post.get('rank', {})
        lines.append(f"| {i}{' 🔥' if i <= 3 else ''} | {post.get('title', '')} | {post.get('entity', '')}{' ⚠️' if post.get('note') else ''} | {r.get('score', '')} | {r.get('audience', '-')} | {r.get('hook', '-')} | {r.get('discuss', '-')} | {r.get('save', '-')} | {r.get('heat', '')} | {r.get('reason', '')} |")
    lines.append('')
    have_img = {f.stem for f in files}
    for i, post in enumerate(posts, 1):
        s = byid[post['id']]
        tags = ' '.join(f'#{t}' for t in post.get('tags', []))
        lines += [f'## {i:02d} {"🔥 今日必发 · " if i <= 3 else ""}{post.get("headline", "")}', '']
        if post.get('note'): lines += [f'> ⚠️ {post["note"]}', '']
        if post['id'] in have_img: lines += [f'![封面](./{date}/{post["id"]}.jpg)', '']
        lines += ['**标题**', '', post.get('title', ''), '', '**正文**', '', post.get('body', '').strip(), '', tags, '', f'原文：{s.get("title", "")}', f'链接：{s.get("link", "")}', '', '<details><summary>封面要点</summary>', '']
        lines += [f'- {x}' for x in post.get('takeaways', [])]
        lines += ['', '</details>', '', '---', '']
        if preview and i == 1:
            log('[xhs] 预览第 1 条：\n' + post.get('title', '') + '\n\n' + post.get('body', '').strip() + '\n\n' + tags)
    dest = publish('cards', date, '\n'.join(lines), files)
    save_topics(repo, token, topics, date, posts)
    top = ' / '.join(p.get('title', '')[:14] for p in posts[:3])
    log(f'[xhs] 生成 {len(posts)} 条文稿、{len(files)} 张封面，今日必发：{top}，写入 {dest}')


def pick_jobs(jobs: list[dict], region: str = '', n: int = 12, per_company: int = 2) -> list[dict]:
    """有真实公司名、未过期；按地区筛；分数高优先；每家公司最多 per_company 条。"""
    cn, ov = {'国内', '深圳', '香港'}, {'海外', '远程'}
    want = cn if region == 'cn' else ov if region == 'overseas' else cn | ov
    pool = [j for j in jobs if j.get('company') and not ANON_RE.search(j['company']) and not j.get('stale') and j.get('region') in want]
    pool.sort(key=lambda j: str(j.get('source_updated', '')), reverse=True)  # 新发布优先
    pool.sort(key=lambda j: -int(j.get('score', 0)))  # 稳定排序：分数高优先，同分按新旧
    out, seen = [], {}
    for j in pool:
        c = j['company']
        if seen.get(c, 0) >= per_company: continue
        seen[c] = seen.get(c, 0) + 1; out.append(j)
        if len(out) >= n: break
    return out


def run_jobs(date: str):
    src = DATA / 'jobs.json'
    if not src.exists(): raise SystemExit(f'没有 {src}')
    data = json.loads(src.read_text())
    region = os.environ.get('XHS_JOBS_REGION', '').strip()
    picked = pick_jobs(data.get('jobs', []), region)
    if len(picked) < 5: log(f'[xhs] 可用岗位只有 {len(picked)} 条，跳过岗位周报'); return
    total = sum(1 for j in data.get('jobs', []) if not j.get('stale'))
    prompt = f'本周可选岗位 {len(picked)} 条（站点共 {total} 条在更新），请生成一篇：\n' + json.dumps([{'company': j['company'], 'title': j['title'], 'location': j.get('location'), 'tags': [t for t in j.get('tags', []) if t not in ('匹配高', '匹配中', '匹配低')], 'reasons': j.get('reasons', []), 'source': j.get('source')} for j in picked], ensure_ascii=False)
    result = call_llm_json(JOBS_SYSTEM, prompt, JOBS_SCHEMA, label='xhs-jobs')
    if not result: raise SystemExit('文本模型未返回岗位文稿')
    post = clean_post(dict(result)); post['id'] = 'cover'
    shorten_titles([post])
    post['tags'] = [JOBS_TAG] + [t for t in post['tags'] if t not in (JOBS_TAG, SERIES_TAG)][:4]
    post['highlights'] = [h for h in result.get('highlights', []) if h.strip()][:6]
    art = None
    _, img_dir, _, _ = out_paths('jobs', date)
    episode = episode_number(os.environ.get('INBOX_REPO', 'lgyStoic/radar-inbox'), os.environ.get('INBOX_TOKEN', '').strip(), 'jobs', date)
    files = render_cards([('cover', card_html(1, post, {'jobs': picked}, date, base64.b64encode(art).decode() if art else None, kind='jobs', episode=episode))], img_dir)

    tags = ' '.join(f'#{t}' for t in post['tags'])
    lines = [f'# AI infra 岗位精选 · {date}', '', '> 自动生成初稿：岗位事实以文末明细表（含链接）为准，发布前逐条核对公司名和岗位名；正文不放链接，不写薪资，不提内推。', '']
    if files: lines += [f'![封面](./{date}/cover.jpg)', '']
    lines += ['**标题**', '', post['title'], '', '**正文**', '', post['body'], '', tags, '', '## 岗位明细（核对用，不发）', '', '| # | 公司 | 岗位 | 地点 | 分数 | 来源 | 链接 |', '|---|---|---|---|---|---|---|']
    lines += [f'| {i} | {j["company"]} | {j["title"]} | {j.get("location", "")} | {j.get("score", "")} | {j.get("source", "")} | {j.get("url", "")} |' for i, j in enumerate(picked, 1)]
    lines += ['', f'筛选：有真实公司名、未过期、地区={region or "全部"}、每家 ≤2 条、按匹配分排序；站点岗位页 https://lgystoic.github.io/radar/jobs/ 共 {total} 条。', '']
    if os.environ.get('XHS_PREVIEW') == '1':
        log('[xhs] 预览岗位周报：\n' + post['title'] + '\n\n' + post['body'] + '\n\n' + tags)
    dest = publish('jobs', date, '\n'.join(lines), files)
    log(f'[xhs] 岗位周报 {len(picked)} 个岗位、{len(files)} 张封面，写入 {dest}')


def last_issue_date(repo: str, token: str, kind_dir: str, date: str) -> str | None:
    """私有仓库里该专题上一期的日期（早于 date 的最新 md）。"""
    if not token: return None
    try:
        names = sorted(e['name'][:-3] for e in gh_get_json(repo, f'posts/{kind_dir}', token) if isinstance(e, dict) and e.get('name', '').endswith('.md') and e['name'][:-3] < date)
        return names[-1] if names else None
    except Exception as e:
        log(f'[xhs] 上一期查询失败：{e}'); return None


def run_track_post(track: dict, date: str):
    """专题日报：自上一期以来的新条目（最多回看 3 天）→ 模型先判值不值得发 → 值得才出文稿 + 封面。"""
    from datetime import timedelta
    src = DATA / 'tracks' / f"{track['id']}.json"
    if not src.exists(): log(f"[xhs] 没有 {src}，先跑 tools/tracks.py"); return
    d = json.loads(src.read_text())
    kind_dir = f"tracks/{track['id']}"
    token, repo = os.environ.get('INBOX_TOKEN', '').strip(), os.environ.get('INBOX_REPO', 'lgyStoic/radar-inbox')
    floor = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=3)).strftime('%Y-%m-%d')
    since = max(last_issue_date(repo, token, kind_dir, date) or floor, floor)
    recent = [e for e in d.get('entries', []) if since < e.get('date', '') <= date]
    if len(recent) < 2: log(f"[xhs] {track['name']}：{since} 之后只有 {len(recent)} 条，今天不发"); return
    tag = TRACK_TAG.get(track['id'], f"{track['name']}日报")
    prompt = json.dumps({'since_last_issue': f'{since} ~ {date}', 'entries': [{'date': e['date'], 'entity': e.get('entity', ''), 'kind': e.get('kind', ''), 'title': e['title'], 'summary': e.get('summary', ''), 'why': e.get('why', ''), 'source': e.get('source', '')} for e in recent[:40]],
                         'context_digest': (d.get('digest') or {}).get('text', ''), 'context_sota': (d.get('sota') or [])[:8]}, ensure_ascii=False)
    result = call_llm_json(TRACK_SYSTEM.format(name=track['name'], tag=tag), prompt, TRACK_SCHEMA, label=f"xhs-track-{track['id']}")
    if not result: raise SystemExit('文本模型未返回专题日报')
    if not result.get('worth'):
        log(f"[xhs] {track['name']}：今天不值得发（{result.get('worth_reason', '')[:60]}），{len(recent)} 条候选"); return
    post = clean_post(dict(result)); post['id'] = 'cover'
    shorten_titles([post])
    post['tags'] = [re.sub(r'[\s#]+', '', tag)] + [t for t in post['tags'] if t not in (tag, SERIES_TAG, JOBS_TAG)][:4]
    post['highlights'] = [h for h in result.get('highlights', []) if h.strip()][:6]
    art = None
    _, img_dir, _, _ = out_paths(kind_dir, date)
    episode = episode_number(repo, token, kind_dir, date)
    files = render_cards([('cover', card_html(1, post, {'track_name': track['name'], 'track_id': track['id'], 'n': len(recent)}, date, base64.b64encode(art).decode() if art else None, kind='track', episode=episode))], img_dir)
    tags = ' '.join(f'#{t}' for t in post['tags'])
    lines = [f"# {track['name']}日报 · {date}" + (f' · 第 {episode} 期' if episode else ''), '', f'> 自动生成初稿：事实以文末条目明细（含链接）为准，发布前逐条核对模型名和数字；正文不放链接。覆盖 {since} 之后的新条目；模型判定值得发的理由：{result.get("worth_reason", "")}。专题页：https://lgystoic.github.io/radar/tracks/{track["id"]}/', '']
    if files: lines += [f'![封面](./{date}/cover.jpg)', '']
    lines += ['**标题**', '', post['title'], '', '**正文**', '', post['body'], '', tags, '', '## 条目明细（核对用，不发）', '', '| 日期 | 主体 | 类型 | 标题 | 来源 | 链接 |', '|---|---|---|---|---|---|']
    lines += [f"| {e['date']} | {e.get('entity', '')} | {e.get('kind', '')} | {e['title']} | {e.get('source', '')} | {e['link']} |" for e in recent]
    if os.environ.get('XHS_PREVIEW') == '1':
        log(f"[xhs] 预览{track['name']}日报：\n" + post['title'] + '\n\n' + post['body'] + '\n\n' + tags)
    dest = publish(kind_dir, date, '\n'.join(lines), files)
    log(f"[xhs] {track['name']}日报 {len(recent)} 条进展、{len(files)} 张封面，写入 {dest}")


def main():
    if '--check-llm' in sys.argv:
        check = call_llm_json('你是连通性检测器。', '只返回 {"ok": true}。', {'type':'object', 'properties':{'ok':{'type':'boolean'}}, 'required':['ok'], 'additionalProperties':False}, label='xhs-check')
        if not check or check.get('ok') is not True: raise SystemExit('LongCat 未返回有效检测结果')
        print('LongCat 文本模型可用'); return
    date = os.environ.get('RADAR_DATE') or datetime.now().strftime('%Y-%m-%d')
    if '--jobs' in sys.argv: run_jobs(date)
    elif '--tracks' in sys.argv:
        for t in load_tracks():
            if t.get('post'):
                try: run_track_post(t, date)
                except SystemExit as e: log(f"[xhs] {t['name']} 日报失败：{e}")
    else: run_cards(date)


if __name__ == '__main__':
    main()
