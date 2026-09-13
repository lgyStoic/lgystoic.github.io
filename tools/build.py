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
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")

ROOT = Path(__file__).resolve().parent.parent
NOTES_JSON = ROOT / "notes" / "notes.json"
RADAR_DIR = ROOT / "radar"
RADAR_DATA = RADAR_DIR / "data"
RADAR_CONFIG = RADAR_DIR / "sources.json"
SITE_URL = "https://lgystoic.github.io"
SITE_TITLE = "Garry 的学习站"
SITE_DESC = "GPU kernel、训练性能、生成模型和城市数据的中文笔记存档。"
LATEST_ON_HOME = 6


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


def render_radar_day_body(day: dict, config: dict, *, collapse_low: bool = True) -> str:
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
    <title>AI 信息雷达 {date} | Garry 的学习站</title>
    <meta name="description" content="{description}" />
    <link rel="canonical" href="{site_url}/radar/{date}/" />
    <meta property="og:type" content="article" />
    <meta property="og:title" content="AI 信息雷达 {date}" />
    <meta property="og:description" content="{description}" />
    <meta property="og:url" content="{site_url}/radar/{date}/" />
    <meta name="twitter:card" content="summary" />
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
    <header class="site-header">
      <div class="wrap">
        <a class="brand" href="../../" aria-label="回到首页">
          <span class="brand-mark">G</span>
          <span>Garry</span>
        </a>
        <nav class="site-nav" aria-label="主导航">
          <a href="../../notes/">笔记</a>
          <a href="../" aria-current="page">雷达</a>
          <a href="https://github.com/lgyStoic" rel="me noreferrer">GitHub</a>
          <button class="theme-toggle" type="button" data-theme-toggle aria-label="切换深浅色">
            <span data-theme-icon>◑</span>
          </button>
        </nav>
      </div>
    </header>

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
        <span>© 2026 Garry · 自动汇总，摘要仅供快速筛选，请以原文为准</span>
        <span><a href="../">全部往期</a> · <a href="../feed.xml">RSS</a></span>
      </div>
    </footer>
    <script src="../../site.js" defer></script>
  </body>
</html>
"""

FAVICON = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%231b1b1a'/%3E%3Ctext x='32' y='43' text-anchor='middle' font-size='32' font-family='Helvetica,Arial' font-weight='700' fill='%23fbfaf8'%3EG%3C/text%3E%3C/svg%3E"


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


def write_radar_days(days: list[dict], config: dict) -> None:
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
            date=esc(day["date"]),
            date_human=esc(human_date(day["date"])),
            description=radar_description(day),
            site_url=SITE_URL,
            favicon=FAVICON,
            pager=" · ".join(pager),
            body=render_radar_day_body(day, config),
        )
        out_dir = RADAR_DIR / day["date"]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(html_text, encoding="utf-8")


def render_radar_latest(days: list[dict], config: dict) -> str:
    if not days:
        return '    <p class="empty-state">第一期还没有生成——每天早上 8 点（北京时间）自动更新。</p>'
    day = days[0]
    head = (
        f'    <div class="section-head"><h2>{esc(human_date(day["date"]))}</h2>'
        f'<a class="text-link" href="./{esc(day["date"])}/">永久链接 →</a></div>'
    )
    return head + "\n" + render_radar_day_body(day, config)


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
        f"    <title>{esc(site.get('title', 'AI 信息雷达'))} | Garry</title>\n"
        f"    <link>{SITE_URL}/radar/</link>\n"
        f"    <description>{esc(site.get('description', ''))}</description>\n"
        "    <language>zh-CN</language>\n"
        f'    <atom:link href="{SITE_URL}/radar/feed.xml" rel="self" type="application/rss+xml" />\n'
        + "\n".join(items)
        + "\n  </channel>\n</rss>\n"
    )
    (RADAR_DIR / "feed.xml").write_text(feed, encoding="utf-8")


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


def write_sitemap(notes: list[dict], days: list[dict]) -> None:
    latest = notes[0].get("updated") if notes else None
    urls = [(f"{SITE_URL}/", latest), (f"{SITE_URL}/notes/", latest)]
    urls += [(SITE_URL + note_href(n, from_root=False), n.get("updated")) for n in notes]
    if days:
        urls.append((f"{SITE_URL}/radar/", days[0]["date"]))
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
    notes = load_notes()
    latest = notes[0].get("updated", "") if notes else ""
    radar_config, days = load_radar()

    inject(
        ROOT / "index.html",
        {
            "latest": render_latest(notes),
            "topics": render_topic_links(notes),
            "stats": f'    <p class="meta-line">{len(notes)} 篇笔记 · 最近更新 {esc(latest)}</p>',
            "radar": render_home_radar(days),
        },
    )
    if (RADAR_DIR / "index.html").exists():
        inject(
            RADAR_DIR / "index.html",
            {
                "radar-latest": render_radar_latest(days, radar_config),
                "radar-days": render_radar_days_list(days),
            },
        )
        write_radar_days(days, radar_config)
        write_radar_feed(days, radar_config)
    inject(
        ROOT / "notes" / "index.html",
        {
            "archive": render_archive(notes),
            "tags": render_tag_filters(notes),
            "count": f'    <p class="result-count" data-result-count>{len(notes)} 篇</p>',
        },
    )
    write_feed(notes)
    write_sitemap(notes, days)
    print(f"已生成：{len(notes)} 篇笔记 · {len(days)} 期雷达 · index.html · notes/index.html · radar/ · feed.xml · sitemap.xml")


if __name__ == "__main__":
    main()
