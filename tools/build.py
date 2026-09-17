#!/usr/bin/env python3
"""从 notes/notes.json 生成静态列表、RSS 和 sitemap。

用法：
    python3 tools/build.py

会改写的内容：
  - index.html       首页「最新笔记」列表、主题标签、统计行、「今日雷达」区块
  - notes/index.html 归档页按年分组的完整列表、标签筛选器、计数
  - radar/index.html 雷达页：最新一期正文 + 往期列表
  - radar/<date>/    每一期的永久链接页（整页生成）
  - radar/feed.xml   雷达 RSS（每期一条）
  - feed.xml         笔记 RSS 2.0
  - sitemap.xml      站点地图

页面里用 <!-- build:xxx --> ... <!-- /build:xxx --> 标记注入区间，
标记之外的排版可以随便改，重新跑脚本不会覆盖。
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")

ROOT = Path(__file__).resolve().parent.parent
NOTES_JSON = ROOT / "notes" / "notes.json"
RADAR_DIR = ROOT / "radar"
RADAR_DATA = RADAR_DIR / "data"
RADAR_CONFIG = RADAR_DIR / "sources.json"
EVENTS_DATA = RADAR_DATA / "events.json"
EVENTS_CONFIG = RADAR_DIR / "event_sources.json"
CHECKS_DIR = RADAR_DIR / "checks"
LAST_RUN = RADAR_DATA / "last-run.json"
SITE_URL = "https://lgystoic.github.io"
SITE_TITLE = json.loads((ROOT / "site.json").read_text(encoding="utf-8")).get("name", "Anaxagore")
SITE_JSON = ROOT / "site.json"
SITE_DESC = "GPU kernel、训练性能、生成模型和城市数据的中文笔记存档。"
LATEST_ON_HOME = 4
GUIDES_DIR = ROOT / "guides"
GUIDES_JSON = GUIDES_DIR / "guides.json"
GUIDE_LINKS = GUIDES_DIR / "links.json"
GUIDE_SUPPORT = GUIDES_DIR / "support.json"


def esc(value: str) -> str:
    return html.escape(str(value or ""), quote=True)


def load_notes() -> list[dict]:
    notes = json.loads(NOTES_JSON.read_text(encoding="utf-8"))
    notes.sort(key=lambda n: (n.get("updated") or "", n.get("title") or ""), reverse=True)
    return notes


def note_href(note: dict, *, from_root: bool) -> str:
    if from_root:
        return note.get("url") or f"./notes/{note['slug']}/"
    return note.get("absoluteUrl") or f"/notes/{note['slug']}/"


def render_post(note: dict, *, from_root: bool) -> str:
    tags = [t for t in note.get("tags", []) if t]
    tag_html = "".join(f"<span>{esc(t)}</span>" for t in tags)
    haystack = " ".join([note.get("title", ""), note.get("summary", ""), note.get("source", ""), *tags]).lower()
    return f"""      <li data-tags="{esc('|'.join(tags))}" data-search="{esc(haystack)}">
        <a class="post" href="{esc(note_href(note, from_root=from_root))}">
          <p class="post-date">{esc(note.get('updated', ''))}</p>
          <h3 class="post-title">{esc(note.get('title', ''))}</h3>
          <p class="post-summary">{esc(note.get('summary', ''))}</p>
          <div class="post-tags">{tag_html}</div>
        </a>
      </li>"""


def render_latest(notes: list[dict]) -> str:
    items = "\n".join(render_post(n, from_root=True) for n in notes[:LATEST_ON_HOME])
    return f'    <ul class="post-list">\n{items}\n    </ul>'


def render_archive(notes: list[dict]) -> str:
    groups: dict[str, list[dict]] = {}
    for note in notes:
        year = (note.get("updated") or "----")[:4]
        groups.setdefault(year, []).append(note)

    blocks = []
    for year in sorted(groups, reverse=True):
        items = "\n".join(render_post(n, from_root=False) for n in groups[year])
        blocks.append(
            f'    <section class="year-group" data-year="{esc(year)}">\n'
            f'      <p class="year-label">{esc(year)}</p>\n'
            f'      <ul class="post-list">\n{items}\n      </ul>\n'
            f"    </section>"
        )
    return "\n".join(blocks)


def tag_counts(notes: list[dict]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for note in notes:
        for tag in note.get("tags", []):
            if tag:
                counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def render_topic_links(notes: list[dict], limit: int = 14) -> str:
    chips = "\n".join(
        f'      <li><a class="tag-chip" href="./notes/?tag={esc(tag)}">{esc(tag)} <b>{count}</b></a></li>'
        for tag, count in tag_counts(notes)[:limit]
    )
    return f'    <ul class="tag-cloud">\n{chips}\n    </ul>'


def render_tag_filters(notes: list[dict], primary: int = 10) -> str:
    """常用标签直接摆出来，长尾折进 <details>，不写 JS 也能展开。"""
    counts = tag_counts(notes)
    head, tail = counts[:primary], counts[primary:]

    def chip(tag: str, count: int) -> str:
        return (
            f'      <li><button class="tag-chip" type="button" data-tag="{esc(tag)}" '
            f'aria-pressed="false">{esc(tag)} <b>{count}</b></button></li>'
        )

    rows = ['      <li><button class="tag-chip" type="button" data-tag="" aria-pressed="true">全部</button></li>']
    rows += [chip(tag, count) for tag, count in head]
    block = '    <ul class="tag-cloud">\n' + "\n".join(rows) + "\n    </ul>"

    if tail:
        extra = "\n".join(chip(tag, count) for tag, count in tail)
        block += (
            '\n    <details class="more-tags">\n'
            f'      <summary>其余 {len(tail)} 个标签</summary>\n'
            f'      <ul class="tag-cloud">\n{extra}\n      </ul>\n'
            "    </details>"
        )
    return block



# ---------------------------------------------------------------- 雷达

PRIORITY_LABEL = {"high": "必看", "medium": "值得看", "low": "其余"}
PRIORITY_ORDER = ("high", "medium", "low")


def load_radar() -> tuple[dict, list[dict]]:
    config = json.loads(RADAR_CONFIG.read_text(encoding="utf-8")) if RADAR_CONFIG.exists() else {}
    days = []
    if RADAR_DATA.exists():
        for path in sorted(RADAR_DATA.glob("????-??-??.json"), reverse=True):
            days.append(json.loads(path.read_text(encoding="utf-8")))
    return config, days


def fmt_time(iso: str) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso[:16]
    return dt.astimezone(SHANGHAI).strftime("%m-%d %H:%M")


def render_radar_item(row: dict, categories: dict) -> str:
    tags = "".join(f"<span>{esc(t)}</span>" for t in (row.get("tags") or [])[:4])
    why = f'<p class="radar-why">{esc(row["why"])}</p>' if row.get("why") else ""
    cat = categories.get(row.get("category", ""), row.get("category", ""))
    time_html = f'<time datetime="{esc(row.get("published", ""))}">{esc(fmt_time(row.get("published", "")))}</time>' if row.get("published") else ""
    return f"""        <li class="radar-item prio-{esc(row['priority'])}">
          <div class="radar-meta"><b class="badge">{esc(row['source'])}</b><span>{esc(cat)}</span>{time_html}</div>
          <h3 class="radar-title"><a href="{esc(row['link'])}" rel="noopener noreferrer">{esc(row['title'])}</a></h3>
          <p class="radar-summary">{esc(row.get('summary', ''))}</p>
          {why}
          <div class="post-tags">{tags}</div>
        </li>"""


def render_radar_day_body(day: dict, config: dict, *, collapse_low: bool = True, events_html: str = "") -> str:
    """一期日报的正文：三个优先级分组，low 默认折叠。"""
    site = config.get("site", {})
    categories = config.get("categories", {})
    max_high = site.get("max_high", 10)
    max_medium = site.get("max_medium", 20)
    groups = {p: [r for r in day.get("items", []) if r.get("priority") == p] for p in PRIORITY_ORDER}

    ok = sum(1 for s in day.get("sources", []) if s.get("ok"))
    total = len(day.get("sources", []))
    failed = [s["name"] for s in day.get("sources", []) if not s.get("ok")]
    mode = f"AI 摘要（{esc(day.get('model', ''))}）" if day.get("ai") else "关键词规则（未配置 API key）"
    failed_html = f'<details class="radar-failed"><summary>{len(failed)} 个源抓取失败</summary><p>{esc("、".join(failed))}</p></details>' if failed else ""
    stats = (
        f'<p class="radar-stats">{len(day.get("items", []))} 条 · 来自 {ok}/{total} 个源 · '
        f'必看 {len(groups["high"])} / 值得看 {len(groups["medium"])} / 其余 {len(groups["low"])} · {mode}</p>'
    )

    parts = [stats, failed_html]
    if events_html:
        parts.append(events_html)
    if not day.get("items"):
        parts.append('<p class="empty-state">这一天没有抓到新内容。</p>')

    for prio in PRIORITY_ORDER:
        rows = groups[prio]
        if not rows:
            continue
        if prio == "high":
            rows = rows[:max_high]
        elif prio == "medium":
            rows = rows[:max_medium]
        items = "\n".join(render_radar_item(r, categories) for r in rows)
        heading = f'<h2 class="radar-heading prio-{prio}">{PRIORITY_LABEL[prio]} <b>{len(groups[prio])}</b></h2>'
        block = f'      <ul class="radar-list">\n{items}\n      </ul>'
        if prio == "low" and collapse_low:
            parts.append(f'<details class="radar-low"><summary>{heading}</summary>\n{block}\n</details>')
        else:
            parts.append(f"{heading}\n{block}")
    return "\n".join(p for p in parts if p)


RADAR_DAY_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>AI 信息雷达 {date} | Anaxagore</title>
    <meta name="description" content="{description}" />
    <link rel="canonical" href="{site_url}/radar/{date}/" />
    <meta property="og:type" content="article" />
    <meta property="og:title" content="AI 信息雷达 {date}" />
    <meta property="og:description" content="{description}" />
    <meta property="og:url" content="{site_url}/radar/{date}/" />
    <meta property="og:image" content="{site_url}/assets/og/radar.png" />
    <meta name="twitter:card" content="summary_large_image" />
    <link rel="alternate" type="application/rss+xml" title="AI 信息雷达" href="../feed.xml" />
    <link rel="icon" href="{favicon}" />
    <link rel="stylesheet" href="../../site.css" />
    <script>
      try {{
        var t = localStorage.getItem("theme");
        if (t === "dark" || t === "light") document.documentElement.dataset.theme = t;
      }} catch (e) {{}}
    </script>
  </head>
  <body>
{header}

    <main class="wrap">
      <section class="intro radar-intro">
        <p class="kicker">AI 信息雷达</p>
        <h1>{date_human}</h1>
        <nav class="radar-pager" aria-label="翻期">{pager}</nav>
      </section>
      <section class="radar-day">
{body}
      </section>
    </main>

    <footer class="site-footer">
      <div class="wrap">
        <span>© 2026 {site_name} · 自动汇总，摘要仅供快速筛选，请以原文为准</span>
        <span><a href="../">全部往期</a> · <a href="../feed.xml">RSS</a></span>
      </div>
    </footer>
    <script src="../../site.js" defer></script>
{analytics}
  </body>
</html>
"""

FAVICON = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%231b1b1a'/%3E%3Ctext x='32' y='43' text-anchor='middle' font-size='32' font-family='Helvetica,Arial' font-weight='700' fill='%23fbfaf8'%3EA%3C/text%3E%3C/svg%3E"


def human_date(date: str) -> str:
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return date
    weekdays = "一二三四五六日"
    return f"{dt.year} 年 {dt.month} 月 {dt.day} 日 · 周{weekdays[dt.weekday()]}"


def radar_description(day: dict) -> str:
    highs = [r["title"] for r in day.get("items", []) if r.get("priority") == "high"][:3]
    if highs:
        return esc("必看：" + "；".join(highs))[:300]
    return esc(f"{len(day.get('items', []))} 条 AI 动态，自动汇总。")


def write_radar_days(days: list[dict], config: dict, events_data: dict | None = None, event_types: dict | None = None) -> None:
    for i, day in enumerate(days):
        newer = days[i - 1]["date"] if i > 0 else None
        older = days[i + 1]["date"] if i + 1 < len(days) else None
        pager = []
        if older:
            pager.append(f'<a href="../{esc(older)}/">← {esc(older)}</a>')
        if newer:
            pager.append(f'<a href="../{esc(newer)}/">{esc(newer)} →</a>')
        else:
            pager.append('<span>最新一期</span>')
        html_text = RADAR_DAY_TEMPLATE.format(
            header=render_site_header(load_site(), "../../", "radar"),
            site_name=esc(SITE_TITLE),
            analytics=render_analytics(load_site()),
            date=esc(day["date"]),
            date_human=esc(human_date(day["date"])),
            description=radar_description(day),
            site_url=SITE_URL,
            favicon=FAVICON,
            pager=" · ".join(pager),
            body=render_radar_day_body(day, config, events_html=render_day_events(day["date"], events_data, event_types or {})),
        )
        out_dir = RADAR_DIR / day["date"]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(html_text, encoding="utf-8")


def render_radar_latest(days: list[dict], config: dict, events_data: dict | None = None, event_types: dict | None = None) -> str:
    if not days:
        return '    <p class="empty-state">第一期还没有生成——每天早上 8 点（北京时间）自动更新。</p>'
    day = days[0]
    head = (
        f'    <div class="section-head"><h2>{esc(human_date(day["date"]))}</h2>'
        f'<a class="text-link" href="./{esc(day["date"])}/">永久链接 →</a></div>'
    )
    ev_html = render_day_events(day["date"], events_data, event_types or {}).replace('href="../events/"', 'href="./events/"')
    return head + "\n" + render_radar_day_body(day, config, events_html=ev_html)


def render_radar_days_list(days: list[dict]) -> str:
    if len(days) <= 1:
        return ""
    rows = []
    for day in days[1:]:
        c = day.get("counts", {})
        highs = [r["title"] for r in day.get("items", []) if r.get("priority") == "high"][:2]
        preview = esc("；".join(highs)) if highs else "无必看条目"
        rows.append(
            f'      <li><a class="post" href="./{esc(day["date"])}/">'
            f'<p class="post-date">{esc(day["date"])} · 必看 {c.get("high", 0)} / 值得看 {c.get("medium", 0)} / 其余 {c.get("low", 0)}</p>'
            f'<p class="post-summary">{preview}</p></a></li>'
        )
    return (
        '    <section class="section">\n      <h2 class="radar-heading">往期</h2>\n      <ul class="post-list">\n'
        + "\n".join(rows)
        + "\n      </ul>\n    </section>"
    )


def render_home_radar(days: list[dict]) -> str:
    if not days:
        return ""
    day = days[0]
    picks = [r for r in day.get("items", []) if r.get("priority") == "high"][:3]
    if not picks:
        picks = [r for r in day.get("items", []) if r.get("priority") == "medium"][:3]
    if not picks:
        return ""
    items = "\n".join(
        f'        <li><a class="post radar-pick" href="{esc(r["link"])}" rel="noopener noreferrer">'
        f'<p class="post-date">{esc(r["source"])}</p>'
        f'<h3 class="post-title">{esc(r["title"])}</h3>'
        f'<p class="post-summary">{esc(r.get("summary", ""))}</p></a></li>'
        for r in picks
    )
    return (
        '    <section class="section">\n'
        f'      <div class="section-head"><h2>今日雷达 <span class="muted-date">{esc(day["date"])}</span></h2>'
        '<a class="text-link" href="./radar/">全部 →</a></div>\n'
        f'      <ul class="post-list">\n{items}\n      </ul>\n'
        '    </section>'
    )


def write_radar_feed(days: list[dict], config: dict) -> None:
    site = config.get("site", {})
    items = []
    for day in days[:30]:
        link = f"{SITE_URL}/radar/{day['date']}/"
        highs = [r for r in day.get("items", []) if r.get("priority") == "high"]
        meds = [r for r in day.get("items", []) if r.get("priority") == "medium"]
        body = ""
        for label, rows in (("必看", highs), ("值得看", meds[:10])):
            if not rows:
                continue
            body += f"<h3>{label}</h3><ul>" + "".join(
                f'<li><a href="{esc(r["link"])}">{esc(r["title"])}</a> — {esc(r.get("summary", ""))}</li>' for r in rows
            ) + "</ul>"
        items.append(
            "    <item>\n"
            f"      <title>AI 信息雷达 {esc(day['date'])}</title>\n"
            f"      <link>{esc(link)}</link>\n"
            f"      <guid isPermaLink=\"true\">{esc(link)}</guid>\n"
            f"      <pubDate>{pubdate(day['date'])}</pubDate>\n"
            f"      <description>{esc(body)}</description>\n"
            "    </item>"
        )
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{esc(site.get('title', 'AI 信息雷达'))} | Anaxagore</title>\n"
        f"    <link>{SITE_URL}/radar/</link>\n"
        f"    <description>{esc(site.get('description', ''))}</description>\n"
        "    <language>zh-CN</language>\n"
        f'    <atom:link href="{SITE_URL}/radar/feed.xml" rel="self" type="application/rss+xml" />\n'
        + "\n".join(items)
        + "\n  </channel>\n</rss>\n"
    )
    (RADAR_DIR / "feed.xml").write_text(feed, encoding="utf-8")



# ---------------------------------------------------------------- 活动清单

WEEKDAYS = "一二三四五六日"


def load_events() -> tuple[dict, dict | None]:
    config = json.loads(EVENTS_CONFIG.read_text(encoding="utf-8")) if EVENTS_CONFIG.exists() else {"types": {}}
    data = json.loads(EVENTS_DATA.read_text(encoding="utf-8")) if EVENTS_DATA.exists() else None
    return config, data


def ev_anchor_date(ev: dict, today: str = "") -> str:
    """排序与分组用的锚点日期——下一步要行动的那天：
    学术截止类用截止日；已经开始（或没有开始日）但还能报名/提交的用截止日；否则用开始日。"""
    start, end, deadline = ev.get("start") or "", ev.get("end") or "", ev.get("deadline") or ""
    if ev.get("event_type") == "deadline" and deadline:
        return deadline
    if deadline and (not start or (today and start < today <= deadline)):
        return deadline
    if today and start and start < today and end and end >= today:
        return end  # 已开始、还没结束、没有截止：锚在结束日，标「进行中」
    return start or deadline


def ev_last_date(ev: dict) -> str:
    """活动彻底过去的日期：结束 / 截止 / 开始里最晚的一个。"""
    return max(ev.get("end") or "", ev.get("deadline") or "", ev.get("start") or "")


def fmt_day(date: str) -> tuple[str, str]:
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return ("待定", "")
    return (f"{dt.month}/{dt.day}", f"周{WEEKDAYS[dt.weekday()]}")


def render_event_row(ev: dict, types: dict, today: str) -> str:
    anchor = ev_anchor_date(ev, today)
    day, wd = fmt_day(anchor)
    if ev.get("event_type") == "deadline":
        label = "投稿截止"
    elif anchor and anchor == ev.get("deadline") and anchor != ev.get("start"):
        label = "提交截止" if ev.get("event_type") in ("hackathon", "competition") else "报名截止"
    elif anchor and anchor == ev.get("end") and anchor != ev.get("start"):
        label = "进行中·止"
    else:
        label = ""
    span = ""
    if ev.get("event_type") != "deadline" and ev.get("start") and ev.get("end") and ev["end"] != ev["start"]:
        span = f'<span class="event-span">→ {esc(ev["end"][5:].replace("-", "/"))}</span>'

    meta = []
    if ev.get("city"):
        meta.append(esc(ev["city"]))
    if ev.get("online") and ev.get("city") != "线上":
        meta.append("可线上")
    meta.append(esc(types.get(ev.get("event_type", ""), ev.get("event_type", ""))))
    if ev.get("fee"):
        meta.append(esc(ev["fee"]))
    if ev.get("organizer"):
        meta.append(esc(ev["organizer"]))
    if ev.get("deadline") and ev.get("event_type") != "deadline" and anchor != ev["deadline"]:
        soon = " soon" if ev["deadline"] <= (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d") else ""
        meta.append(f'<b class="ddl{soon}">报名截止 {esc(ev["deadline"][5:].replace("-", "/"))}</b>')
    if anchor == ev.get("deadline") and ev.get("start") and ev.get("start") != anchor:
        verb = "会议" if ev.get("event_type") == "deadline" else ("已开始" if ev["start"] < today else "开始")
        meta.append(f'{verb} {esc(ev["start"][5:].replace("-", "/"))}')
    meta.append(f'<span class="event-src">{esc(ev.get("source", ""))}</span>')

    tags = [ev.get("city", ""), ev.get("event_type", "")]
    if ev.get("online"):
        tags.append("线上")
    if ev.get("relevance") == "high":
        tags.append("推荐")
    haystack = " ".join([ev.get("title", ""), ev.get("summary", ""), ev.get("city", ""), ev.get("organizer", ""), ev.get("source", "")]).lower()
    star = '<span class="star" title="和你的方向高度相关">★</span>' if ev.get("relevance") == "high" else ""
    new = '<span class="new-badge">新</span>' if ev.get("found") == today else ""

    return f"""        <li class="event-row rel-{esc(ev.get('relevance', 'medium'))}" data-tags="{esc('|'.join(t for t in tags if t))}" data-search="{esc(haystack)}">
          <div class="event-date"><b>{esc(day)}</b><span>{esc(label or wd)}</span></div>
          <div class="event-body">
            <h3 class="event-title">{star}<a href="{esc(ev['link'])}" rel="noopener noreferrer">{esc(ev['title'])}</a>{span}{new}</h3>
            <p class="event-meta">{" · ".join(m for m in meta if m)}</p>
            <p class="event-summary">{esc(ev.get('summary', ''))}</p>
          </div>
        </li>"""


def render_events_page(config: dict, data: dict | None) -> dict[str, str]:
    types = config.get("types", {})
    if not data or not data.get("events"):
        return {
            "events-filters": "",
            "events-stats": '    <p class="empty-state">活动清单还没有生成——每天早上 8 点自动更新。</p>',
            "events-list": "",
            "events-past": "",
        }
    today = data.get("today") or datetime.now(SHANGHAI).strftime("%Y-%m-%d")
    events = data["events"]
    alive = [e for e in events if (ev_last_date(e) or today) >= today]
    past = [e for e in events if e not in alive]
    lowrel = [e for e in alive if e.get("relevance") == "low"]
    upcoming = [e for e in alive if e.get("relevance") != "low"]
    upcoming.sort(key=lambda e: (ev_anchor_date(e, today) or "9999", e.get("title", "")))

    # 筛选器：城市 → 线上 → 类型，只列出实际出现过的
    counts: dict[str, int] = {}
    for e in upcoming:
        for t in {e.get("city", ""), e.get("event_type", ""), "线上" if e.get("online") else "", "推荐" if e.get("relevance") == "high" else ""}:
            if t:
                counts[t] = counts.get(t, 0) + 1
    order = ["推荐", *config.get("site", {}).get("cities", []), "线上", *types.keys()]
    chips = ['      <li><button class="tag-chip" type="button" data-tag="" aria-pressed="true">全部</button></li>']
    listed = set()
    for key in order + sorted(k for k in counts if k not in order):
        if key in counts and key not in listed:
            listed.add(key)
            chips.append(f'      <li><button class="tag-chip" type="button" data-tag="{esc(key)}" aria-pressed="false">{esc(types.get(key, key))} <b>{counts[key]}</b></button></li>')
    filters = '    <ul class="tag-cloud">\n' + "\n".join(chips) + "\n    </ul>"

    ok = sum(1 for s in data.get("sources", []) if s.get("ok"))
    total = len(data.get("sources", []))
    mode = f"AI 抽取（{esc(data['model'])}）" if data.get("model") else "规则默认值（未配置 API key）"
    stats = f'    <p class="radar-stats" data-result-count data-unit="个活动">{len(upcoming)} 个即将发生（另 {len(lowrel)} 个低相关已折叠） · 来自 {ok}/{total} 个源 · 更新 {esc(today)} · {mode}</p>'

    groups: dict[str, list[dict]] = {}
    for e in upcoming:
        anchor = ev_anchor_date(e, today)
        key = anchor[:7] if anchor else "9999-99"
        groups.setdefault(key, []).append(e)
    blocks = []
    for key in sorted(groups):
        if key == "9999-99":
            label = "日期待定"
        else:
            y, m = key.split("-")
            label = f"{y} 年 {int(m)} 月"
        rows = "\n".join(render_event_row(e, types, today) for e in groups[key])
        blocks.append(
            f'    <section class="year-group">\n      <p class="year-label">{esc(label)}</p>\n      <ul class="event-list">\n{rows}\n      </ul>\n    </section>'
        )
    listing = "\n".join(blocks)

    tail = []
    if lowrel:
        lowrel.sort(key=lambda e: ev_anchor_date(e, today) or "9999")
        rows = "\n".join(render_event_row(e, types, today) for e in lowrel)
        tail.append(f'    <details class="radar-low"><summary><h2 class="radar-heading">可能不相关 <b>{len(lowrel)}</b></h2></summary>\n      <ul class="event-list">\n{rows}\n      </ul>\n    </details>')
    if past:
        rows = "\n".join(render_event_row(e, types, today) for e in sorted(past, key=ev_last_date, reverse=True))
        tail.append(f'    <details class="radar-low"><summary><h2 class="radar-heading">已结束 <b>{len(past)}</b></h2></summary>\n      <ul class="event-list">\n{rows}\n      </ul>\n    </details>')
    return {"events-filters": filters, "events-stats": stats, "events-list": listing, "events-past": "\n".join(tail)}


def render_home_events(data: dict | None, types: dict) -> str:
    if not data or not data.get("events"):
        return ""
    today = data.get("today") or datetime.now(SHANGHAI).strftime("%Y-%m-%d")
    picks = sorted(
        [e for e in data["events"] if (ev_last_date(e) or today) >= today and e.get("relevance") != "low"],
        key=lambda e: ev_anchor_date(e, today) or "9999",
    )[:4]
    if not picks:
        return ""
    rows = []
    for e in picks:
        day, wd = fmt_day(ev_anchor_date(e, today))
        meta = " · ".join(x for x in [e.get("city", ""), types.get(e.get("event_type", ""), ""), e.get("fee", "")] if x)
        rows.append(
            f'        <li><a class="post radar-pick" href="{esc(e["link"])}" rel="noopener noreferrer">'
            f'<p class="post-date">{esc(day)} {esc(wd)} · {esc(meta)}</p>'
            f'<h3 class="post-title">{esc(e["title"])}</h3>'
            f'<p class="post-summary">{esc(e.get("summary", ""))}</p></a></li>'
        )
    return (
        '    <section class="section">\n'
        '      <div class="section-head"><h2>近期活动</h2><a class="text-link" href="./radar/events/">全部 →</a></div>\n'
        f'      <ul class="post-list">\n' + "\n".join(rows) + "\n      </ul>\n    </section>"
    )


def render_day_events(date: str, data: dict | None, types: dict) -> str:
    """雷达简报里不再嵌活动列表，只留一行指向活动清单的提示。"""
    if not data:
        return ""
    found = [e for e in data.get("events", []) if e.get("found") == date and e.get("relevance") != "low"]
    if not found:
        return ""
    return (
        f'<p class="radar-events-link">当天新发现 <b>{len(found)}</b> 个活动，已归入 '
        f'<a class="text-link" href="../events/">活动清单 →</a></p>'
    )



# ---------------------------------------------------------------- 状态页


def render_status(days: list[dict], events_data: dict | None) -> dict[str, str]:
    # 最近一次运行
    run = json.loads(LAST_RUN.read_text(encoding="utf-8")) if LAST_RUN.exists() else None
    if run:
        started = fmt_time(run.get("started_at", "")) or run.get("started_at", "")
        ev = {"schedule": "定时", "workflow_dispatch": "手动", "push": "触发文件"}.get(run.get("event", ""), run.get("event", ""))
        run_html = (
            f'    <p class="radar-stats">最近一次运行：#{esc(str(run.get("run_number", "")))} · {esc(ev)} · {esc(started)}（北京时间） · '
            f'<a href="{esc(run.get("url", "#"))}" rel="noreferrer">Actions 日志</a></p>'
        )
    else:
        run_html = '    <p class="radar-stats">还没有运行记录。</p>'

    # 巡检报告（最近 14 天）
    reports = sorted(CHECKS_DIR.glob("????-??-??.md"), reverse=True)[:14] if CHECKS_DIR.exists() else []
    blocks = []
    for path in reports:
        lines = [l.rstrip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not lines:
            continue
        head, body = lines[0], lines[1:]
        warn = any(l.startswith("问题：") and not l.startswith("问题：无") for l in body)
        cls = " has-issue" if warn else ""
        items = "".join(f"<li>{esc(l)}</li>" for l in body)
        blocks.append(f'      <li class="check{cls}"><h3>{esc(head)}</h3><ul>{items}</ul></li>')
    checks_html = ('    <ul class="check-list">\n' + "\n".join(blocks) + "\n    </ul>") if blocks else '    <p class="empty-state">还没有巡检报告。</p>'

    # 源健康表：简报 + 活动
    rows = []
    def add_rows(kind: str, sources: list[dict]):
        for s in sources:
            total = s.get("total", s.get("count", 0))
            if not s.get("ok"):
                state, label = "bad", "失败"
            elif total == 0:
                state, label = "warn", "解析 0 条"
            elif s.get("count", 0) == 0:
                state, label = "ok", "无新内容"
            else:
                state, label = "ok", "正常"
            err = esc(s.get("error", "")[:90])
            rows.append(f'        <tr class="src-{state}"><td>{esc(kind)}</td><td>{esc(s["name"])}</td><td><b>{label}</b></td><td>{s.get("count", 0)} / {total}</td><td class="err">{err}</td></tr>')
    if days:
        add_rows("简报", days[0].get("sources", []))
    if events_data:
        add_rows("活动", events_data.get("sources", []))
    if rows:
        ok_n = sum(1 for r in rows if "src-ok" in r); bad_n = sum(1 for r in rows if "src-bad" in r)
        table = (
            f'    <p class="radar-stats">{len(rows)} 个源 · 通 {ok_n} · 失败 {bad_n} · 其余抓通但解析出 0 条</p>\n'
            '    <div class="table-wrap"><table class="src-table">\n'
            '      <thead><tr><th>栏目</th><th>源</th><th>状态</th><th>新 / 总</th><th>错误</th></tr></thead>\n      <tbody>\n'
            + "\n".join(rows) + "\n      </tbody>\n    </table></div>"
        )
    else:
        table = '    <p class="empty-state">还没有源的运行记录。</p>'

    ai_line = ""
    if days:
        d = days[0]
        ai_line = f'    <p class="radar-stats">今日简报：{len(d.get("items", []))} 条 · ' + (f'AI 摘要（{esc(d.get("model", ""))}）' if d.get("ai") else "关键词规则") + "</p>"
    if events_data:
        ai_line += f'\n    <p class="radar-stats">活动清单：{len(events_data.get("events", []))} 条 · ' + (f'AI 抽取（{esc(events_data.get("model", ""))}）' if events_data.get("model") else "规则默认值") + "</p>"

    site = load_site()
    dash = analytics_dashboard(site)
    if dash:
        vis = "公开" if (site.get("analytics") or {}).get("public") else "仅站长可见"
        run_html += f'\n    <p class="radar-stats">访问统计：GoatCounter（{vis}） · <a href="{esc(dash)}" rel="noreferrer">看板</a> · 记录来源站、UTM、每页访问和推荐位点击</p>'
    else:
        run_html += '\n    <p class="radar-stats">访问统计：未启用（site.json → analytics.code 为空）</p>'
    return {"status-run": run_html + ("\n" + ai_line if ai_line else ""), "status-checks": checks_html, "status-sources": table}



# ---------------------------------------------------------------- 门户卡片（由 site.json 生成）


def load_site() -> dict:
    return json.loads(SITE_JSON.read_text(encoding="utf-8")) if SITE_JSON.exists() else {"modules": []}


def module_status(mod: dict, notes: list[dict], days: list[dict], events_data: dict | None) -> str:
    kind = mod.get("status")
    if kind == "notes":
        latest = notes[0].get("updated", "") if notes else ""
        return f"{len(notes)} 篇 · 最近 {esc(latest[5:].replace('-', '/'))}" if notes else "还没有笔记"
    if kind == "radar":
        if not days:
            return "第一期还没生成"
        d = days[0]
        c = d.get("counts", {})
        mode = esc(d.get("model", "")) if d.get("ai") else "规则"
        return f"{esc(d['date'][5:].replace('-', '/'))} · {len(d.get('items', []))} 条 · 必看 {c.get('high', 0)} · {mode}"
    if kind == "events":
        if not events_data or not events_data.get("events"):
            return "清单还没生成"
        today = events_data.get("today") or datetime.now(SHANGHAI).strftime("%Y-%m-%d")
        alive = [e for e in events_data["events"] if (ev_last_date(e) or today) >= today and e.get("relevance") != "low"]
        week_end = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d")
        this_week = [e for e in alive if today <= (ev_anchor_date(e, today) or "9999") <= week_end]
        local = [e for e in alive if e.get("city") in ("深圳", "广州", "香港")]
        return f"即将 {len(alive)} 个 · 本周 {len(this_week)} · 深广港 {len(local)}"
    if kind == "guides":
        guides, _ = load_guides()
        pub = [g for g in guides if g.get("status") == "published"]
        if not pub:
            return f"{len(guides)} 步 · 整理中"
        latest = max(g.get("updated", "") for g in pub)
        return f"{len(pub)} / {len(guides)} 步已发布 · 最近 {esc(latest[5:].replace('-', '/'))}"
    if kind == "inbox":
        return "私有仓库 · 手机一键投递"
    if kind == "status":
        run = json.loads(LAST_RUN.read_text(encoding="utf-8")) if LAST_RUN.exists() else None
        if not run:
            return "还没有运行记录"
        ev = {"schedule": "定时", "workflow_dispatch": "手动", "push": "触发"}.get(run.get("event", ""), run.get("event", ""))
        return f"最近运行 #{run.get('run_number', '')} · {esc(ev)} · {esc(fmt_time(run.get('started_at', '')))}"
    return ""


def render_cards(site: dict, notes: list[dict], days: list[dict], events_data: dict | None) -> str:
    cards = []
    for mod in site.get("modules", []):
        if mod.get("card") is False:
            continue
        href = mod["path"]
        if href.startswith("/"):
            href = "." + href
        attrs = ' rel="noreferrer"' if href.startswith("http") else ""
        lock = ' <span class="card-lock" title="私有">🔒</span>' if mod.get("private") else ""
        status = module_status(mod, notes, days, events_data)
        cards.append(
            f'      <li><a class="card" href="{esc(href)}"{attrs}>'
            f'<p class="card-role">{esc(mod.get("role", ""))}</p>'
            f'<h3 class="card-name">{esc(mod["name"])}{lock}</h3>'
            f'<p class="card-blurb">{esc(mod.get("blurb", ""))}</p>'
            f'<p class="card-status">{status}</p></a></li>'
        )
    return '    <ul class="card-grid">\n' + "\n".join(cards) + "\n    </ul>"


# ---------------------------------------------------------------- 指南 / 推广链接

def load_guides() -> tuple[list[dict], dict]:
    guides = json.loads(GUIDES_JSON.read_text(encoding="utf-8")) if GUIDES_JSON.exists() else []
    links = json.loads(GUIDE_LINKS.read_text(encoding="utf-8")) if GUIDE_LINKS.exists() else {}
    return sorted(guides, key=lambda g: g.get("step", 0)), links


def guide_href(g: dict, *, from_root: bool) -> str:
    return ("." + g["path"]) if from_root else ("./" + g["path"].split("/guides/", 1)[1])


def render_guides_path(guides: list[dict]) -> str:
    rows = []
    for g in guides:
        published = g.get("status") == "published"
        title = esc(g["title"])
        head = f'<a href="{esc(guide_href(g, from_root=False))}">{title}</a>'
        meta = f'更新于 {esc(g["updated"])}' if published and g.get("updated") else "草稿 · 整理中，可先看"
        cls = "guide-step" + ("" if published else " is-draft")
        rows.append(
            f'      <li class="{cls}"><span class="guide-num">{g.get("step", "")}</span>'
            f'<div><h3>{head}</h3><p>{esc(g.get("blurb", ""))}</p><p class="guide-meta">{meta}</p></div></li>'
        )
    return '    <ol class="guide-path">\n' + "\n".join(rows) + "\n    </ol>"


_OFFER_RE = re.compile(r'(<div class="offer"[^>]*\bdata-aff="([^"]+)"[^>]*>)(.*?)(</div>)', re.DOTALL)
_INLINE_AFF_RE = re.compile(r'<a\b([^>]*)\bdata-aff="([^"]+)"([^>]*)>')


def _set_attr(tag: str, name: str, value: str | None) -> str:
    """把 <a …> 开标签里的某个属性设为 value；value 为 None 时删除。"""
    tag = re.sub(rf'\s{re.escape(name)}(="[^"]*")?(?=[\s>])', "", tag)
    if value is None:
        return tag
    return tag[:-1] + f' {name}="{esc(value)}">'


def apply_affiliate_links(path: Path, links: dict) -> tuple[int, int]:
    """填充推广链接。空链接的 .offer 整块 hidden；返回 (已填, 已隐藏)。幂等。"""
    table = links.get("links", {})
    text = path.read_text(encoding="utf-8")
    filled = hidden = 0

    def offer(m: re.Match) -> str:
        nonlocal filled, hidden
        open_tag, key, body, close = m.groups()
        url = (table.get(key) or {}).get("url", "").strip()
        open_tag = re.sub(r"\s+hidden(?=[\s>])", "", open_tag)
        if url:
            filled += 1
            body = re.sub(r'(<a\b[^>]*\bdata-aff-link\b[^>]*)\bhref="[^"]*"', lambda a: a.group(1) + f'href="{esc(url)}"', body)
        else:
            hidden += 1
            open_tag = open_tag[:-1] + " hidden>"
            body = re.sub(r'(<a\b[^>]*\bdata-aff-link\b[^>]*)\bhref="[^"]*"', lambda a: a.group(1) + 'href="#"', body)
        return open_tag + body + close

    text = _OFFER_RE.sub(offer, text)

    def inline(m: re.Match) -> str:
        nonlocal filled
        before, key, after = m.groups()
        tag = f"<a{before}data-aff=\"{key}\"{after}>"
        url = (table.get(key) or {}).get("url", "").strip()
        if url:
            filled += 1
            tag = _set_attr(tag, "href", url)
            tag = _set_attr(tag, "rel", "sponsored noopener noreferrer")
            tag = _set_attr(tag, "class", "aff")
        else:
            tag = _set_attr(tag, "href", None)
            tag = _set_attr(tag, "rel", None)
            tag = _set_attr(tag, "class", "aff aff-off")
        return tag

    text = _INLINE_AFF_RE.sub(inline, text)

    disclosure = esc(links.get("disclosure", ""))
    text = re.sub(
        r'(<p class="disclosure" data-disclosure[^>]*>).*?(</p>)',
        lambda m: m.group(1) + disclosure + m.group(2),
        text,
        flags=re.DOTALL,
    )
    path.write_text(text, encoding="utf-8")
    return filled, hidden


def apply_guide_support(path: Path, *, from_index: bool = False) -> None:
    """Insert the optional support card into every current and future guide."""
    config = json.loads(GUIDE_SUPPORT.read_text(encoding="utf-8")) if GUIDE_SUPPORT.exists() else {}
    prefix = "../" if from_index else "../../"
    methods = []
    for key, label in (("wechat_image", "微信"), ("alipay_image", "支付宝")):
        image = str(config.get(key, "")).strip().lstrip("/")
        if image:
            methods.append(
                f'<figure class="support-method"><img src="{prefix}{esc(image)}" alt="{label}打赏码" '
                f'loading="lazy" width="220" height="220"><figcaption>{label}</figcaption></figure>'
            )
    hidden = "" if config.get("enabled") and methods else " hidden"
    block = (
        f'<!-- build:guide-support -->\n<section class="guide-support" data-support{hidden}>'
        f'<div><p class="kicker">Support</p><h2>{esc(config.get("title", "支持继续创作"))}</h2>'
        f'<p>{esc(config.get("description", ""))}</p><p class="support-note">完全自愿，所有指南免费阅读。</p></div>'
        f'<div class="support-methods">{"".join(methods)}</div></section>\n<!-- /build:guide-support -->'
    )
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'<!-- build:guide-support -->.*?<!-- /build:guide-support -->', block, text, flags=re.DOTALL)
    if "build:guide-support" not in text:
        anchor = '<div class="share" data-share>' if not from_index else '</main>'
        text = text.replace(anchor, block + "\n\n      " + anchor, 1)
    path.write_text(text, encoding="utf-8")


def render_guide_jsonld(g: dict, page: Path) -> str:
    """给指南子页生成 BreadcrumbList + HowTo 结构化数据（步骤取自 <ol class="steps">）。"""
    html = page.read_text(encoding="utf-8")
    url = SITE_URL + g["path"]
    steps = []
    for li in re.findall(r'<ol class="steps">(.*?)</ol>', html, re.DOTALL):
        for name, body in re.findall(r"<h3>(.*?)</h3>\s*<p>(.*?)</p>", li, re.DOTALL):
            steps.append({"@type": "HowToStep", "name": re.sub(r"<[^>]+>", "", name).strip(),
                          "text": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", body)).strip()})
    desc_m = re.search(r'<meta name="description" content="([^"]*)"', html)
    data = [
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": SITE_TITLE, "item": SITE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": "上手指南", "item": SITE_URL + "/guides/"},
            {"@type": "ListItem", "position": 3, "name": g["title"], "item": url}]},
        {"@context": "https://schema.org", "@type": "HowTo", "name": g["title"],
         "description": desc_m.group(1) if desc_m else g.get("blurb", ""),
         "inLanguage": "zh-CN", "url": url, "dateModified": g.get("updated", ""),
         "author": {"@type": "Person", "name": SITE_TITLE, "url": SITE_URL + "/about/"},
         "step": steps},
    ]
    return "\n".join(f'    <script type="application/ld+json">{json.dumps(d, ensure_ascii=False)}</script>' for d in data)

def build_guides() -> list[dict]:
    if not (GUIDES_DIR / "index.html").exists():
        return []
    guides, links = load_guides()
    inject(GUIDES_DIR / "index.html", {"guides-path": render_guides_path(guides)})
    apply_guide_support(GUIDES_DIR / "index.html", from_index=True)
    by_dir = {g["path"].rstrip("/").rsplit("/", 1)[-1]: g for g in guides}
    for page in sorted(GUIDES_DIR.glob("*/index.html")):
        filled, hidden = apply_affiliate_links(page, links)
        apply_guide_support(page)
        g = by_dir.get(page.parent.name)
        if g and "build:jsonld" in page.read_text(encoding="utf-8"):
            inject(page, {"jsonld": render_guide_jsonld(g, page)})
        print(f"guides/{page.parent.name}: 推广位 {filled} 个已填 · {hidden} 个隐藏")
    return guides


# ---------------------------------------------------------------- 访问统计（GoatCounter）

ANALYTICS_EVENTS_JS = """(function(){
  function gc(){return window.goatcounter&&window.goatcounter.count?window.goatcounter:null}
  function send(path,title){var g=gc();if(g)g.count({path:path,title:title||path,event:true})}
  document.addEventListener("click",function(e){
    var a=e.target.closest&&e.target.closest("a");
    if(!a)return;
    var offer=a.closest(".offer");
    if(a.hasAttribute("data-aff-link")||a.hasAttribute("data-aff")||(a.rel||"").indexOf("sponsored")>-1){
      var key=(offer&&offer.getAttribute("data-aff"))||a.getAttribute("data-aff")||"link";
      send("aff/"+key,"推荐位："+key+" @ "+location.pathname);return}
    if(a.host&&a.host!==location.host){send("out/"+a.host,"外链："+a.host+" @ "+location.pathname)}
  });
  document.addEventListener("click",function(e){
    var b=e.target.closest&&e.target.closest("[data-share-copy],[data-share-native]");
    if(b)send("share/"+(b.hasAttribute("data-share-copy")?"copy":"native"),"分享 @ "+location.pathname)
  });
})();"""


def render_analytics(site: dict) -> str:
    """GoatCounter 计数脚本 + 推荐位 / 外链 / 分享事件埋点。code 为空则输出空字符串。"""
    a = site.get("analytics") or {}
    code = (a.get("code") or "").strip()
    if not code or a.get("provider", "goatcounter") != "goatcounter":
        return ""
    return (
        f'    <script data-goatcounter="https://{esc(code)}.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>\n'
        f"    <script>{ANALYTICS_EVENTS_JS}</script>"
    )


def analytics_dashboard(site: dict) -> str:
    a = site.get("analytics") or {}
    code = (a.get("code") or "").strip()
    return f"https://{code}.goatcounter.com" if code else ""


# ---------------------------------------------------------------- 站点公共头部

def page_prefix(rel_path: str) -> str:
    """页面相对站点根的路径（如 'guides/pc/index.html'）→ 回到根目录的前缀。"""
    depth = rel_path.count("/")
    return "./" if depth == 0 else "../" * depth


def current_module(site: dict, url_path: str) -> str | None:
    """按最长路径前缀匹配当前页面属于哪个导航模块。"""
    best, best_len = None, -1
    for mod in site.get("modules", []):
        p = mod.get("path", "")
        if p.startswith("/") and url_path.startswith(p) and len(p) > best_len:
            best, best_len = mod["id"], len(p)
    return best


def render_site_header(site: dict, prefix: str, current: str | None) -> str:
    mods = {m["id"]: m for m in site.get("modules", [])}
    links = []
    for mid in site.get("nav", []):
        m = mods.get(mid)
        if not m:
            continue
        href = m["path"]
        href = (prefix + href.lstrip("/")) if href.startswith("/") else href
        if prefix == "/":
            href = m["path"]
        cur = ' aria-current="page"' if mid == current else ""
        links.append(f'          <a href="{esc(href)}"{cur}>{esc(m.get("nav_label", m["name"]))}</a>')
    home = "/" if prefix == "/" else prefix
    name = esc(site.get("name", SITE_TITLE))
    return (
        '    <header class="site-header">\n'
        '      <div class="wrap">\n'
        f'        <a class="brand" href="{home}" aria-label="首页">\n'
        f'          <span class="brand-mark">{esc(name[:1])}</span>\n'
        f'          <span>{name}</span>\n'
        '        </a>\n'
        '        <nav class="site-nav" aria-label="主导航">\n'
        + "\n".join(links) + "\n"
        '          <button class="theme-toggle" type="button" data-theme-toggle aria-label="切换深浅色">\n'
        '            <span data-theme-icon>◑</span>\n'
        '          </button>\n'
        '        </nav>\n'
        '      </div>\n'
        '    </header>'
    )


def inject_site_chrome(site: dict) -> int:
    """给所有带 <!-- build:header --> 的页面生成头部；带 build:site-name 的位置填站名。"""
    n = 0
    for page in sorted(ROOT.glob("**/*.html")):
        rel = page.relative_to(ROOT).as_posix()
        if rel.startswith(("radar/20", "node_modules/", "templates/")):
            continue
        text = page.read_text(encoding="utf-8")
        blocks = {}
        if "<!-- build:header -->" in text:
            if rel == "404.html":
                prefix, current = "/", None
            else:
                prefix = page_prefix(rel)
                url_path = "/" + rel[: -len("index.html")] if rel.endswith("index.html") else "/" + rel
                current = current_module(site, url_path)
            blocks["header"] = render_site_header(site, prefix, current)
        if "<!-- build:site-name -->" in text:
            blocks["site-name"] = esc(site.get("name", SITE_TITLE))
        if "<!-- build:analytics -->" in text:
            blocks["analytics"] = render_analytics(site)
        if blocks:
            inject(page, blocks)
            n += 1
    return n


def inject(path: Path, blocks: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    for name, content in blocks.items():
        pattern = re.compile(
            rf"(<!-- build:{re.escape(name)} -->)(.*?)(<!-- /build:{re.escape(name)} -->)",
            re.DOTALL,
        )
        if not pattern.search(text):
            raise SystemExit(f"{path}: 缺少 <!-- build:{name} --> 标记")
        text = pattern.sub(lambda m: f"{m.group(1)}\n{content}\n    {m.group(3)}", text)
    path.write_text(text, encoding="utf-8")


def pubdate(value: str) -> str:
    try:
        dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        dt = datetime.now(timezone.utc)
    return format_datetime(dt)


def write_feed(notes: list[dict]) -> None:
    items = []
    for note in notes:
        link = SITE_URL + note_href(note, from_root=False)
        items.append(
            "    <item>\n"
            f"      <title>{esc(note.get('title', ''))}</title>\n"
            f"      <link>{esc(link)}</link>\n"
            f"      <guid isPermaLink=\"true\">{esc(link)}</guid>\n"
            f"      <pubDate>{pubdate(note.get('updated', ''))}</pubDate>\n"
            f"      <description>{esc(note.get('summary', ''))}</description>\n"
            + "".join(f"      <category>{esc(t)}</category>\n" for t in note.get("tags", []))
            + "    </item>"
        )
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{esc(SITE_TITLE)}</title>\n"
        f"    <link>{SITE_URL}/</link>\n"
        f"    <description>{esc(SITE_DESC)}</description>\n"
        "    <language>zh-CN</language>\n"
        f'    <atom:link href="{SITE_URL}/feed.xml" rel="self" type="application/rss+xml" />\n'
        f"    <lastBuildDate>{pubdate(notes[0].get('updated', '') if notes else '')}</lastBuildDate>\n"
        + "\n".join(items)
        + "\n  </channel>\n</rss>\n"
    )
    (ROOT / "feed.xml").write_text(feed, encoding="utf-8")


def write_sitemap(notes: list[dict], days: list[dict], guides: list[dict] | None = None) -> None:
    latest = notes[0].get("updated") if notes else None
    urls = [(f"{SITE_URL}/", latest), (f"{SITE_URL}/notes/", latest), (f"{SITE_URL}/about/", None)]
    urls.append((f"{SITE_URL}/radar/jobs/", None))
    urls.append((f"{SITE_URL}/radar/contributions/", None))
    urls += [(SITE_URL + note_href(n, from_root=False), n.get("updated")) for n in notes]
    pub = [g for g in (guides or []) if g.get("status") == "published"]
    if pub:
        urls.append((f"{SITE_URL}/guides/", max(g.get("updated", "") for g in pub) or None))
        urls += [(SITE_URL + g["path"], g.get("updated")) for g in pub]
    if days:
        urls.append((f"{SITE_URL}/radar/", days[0]["date"]))
        urls.append((f"{SITE_URL}/radar/events/", days[0]["date"]))
        urls += [(f"{SITE_URL}/radar/{d['date']}/", d["date"]) for d in days]
    body = "\n".join(
        f"  <url>\n    <loc>{esc(loc)}</loc>\n"
        + (f"    <lastmod>{esc(mod)}</lastmod>\n" if mod else "")
        + "  </url>"
        for loc, mod in urls
    )
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n</urlset>\n",
        encoding="utf-8",
    )


def main() -> None:
    from jobs import render as render_jobs
    inject(ROOT / "radar/jobs/index.html", {"jobs": render_jobs()})
    from contributions import render as render_contributions
    inject(ROOT / "radar/contributions/index.html", {"contributions": render_contributions()})
    notes = load_notes()
    latest = notes[0].get("updated", "") if notes else ""
    radar_config, days = load_radar()
    events_config, events_data = load_events()
    event_types = events_config.get("types", {})

    site = load_site()
    inject_site_chrome(site)
    inject(
        ROOT / "index.html",
        {
            "cards": render_cards(site, notes, days, events_data),
            "latest": render_latest(notes),
            "radar": render_home_radar(days),
            "events": render_home_events(events_data, event_types),
        },
    )
    if (RADAR_DIR / "events" / "index.html").exists():
        inject(RADAR_DIR / "events" / "index.html", render_events_page(events_config, events_data))
    if (ROOT / "status" / "index.html").exists():
        inject(ROOT / "status" / "index.html", render_status(days, events_data))
    if (RADAR_DIR / "index.html").exists():
        inject(
            RADAR_DIR / "index.html",
            {
                "radar-latest": render_radar_latest(days, radar_config, events_data, event_types),
                "radar-days": render_radar_days_list(days),
            },
        )
        write_radar_days(days, radar_config, events_data, event_types)
        write_radar_feed(days, radar_config)
    inject(
        ROOT / "notes" / "index.html",
        {
            "archive": render_archive(notes),
            "tags": render_tag_filters(notes),
            "count": f'    <p class="result-count" data-result-count>{len(notes)} 篇</p>',
        },
    )
    guides = build_guides()
    write_feed(notes)
    write_sitemap(notes, days, guides)
    print(f"已生成：{len(notes)} 篇笔记 · {len(days)} 期雷达 · index.html · notes/index.html · radar/ · feed.xml · sitemap.xml")


if __name__ == "__main__":
    main()
