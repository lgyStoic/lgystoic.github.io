#!/usr/bin/env python3
"""从 notes/notes.json 生成静态列表、RSS 和 sitemap。

用法：
    python3 tools/build.py

会改写的内容：
  - index.html       首页「最新笔记」列表、主题标签、统计行
  - notes/index.html 归档页按年分组的完整列表、标签筛选器、计数
  - feed.xml         RSS 2.0
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

ROOT = Path(__file__).resolve().parent.parent
NOTES_JSON = ROOT / "notes" / "notes.json"
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


def write_sitemap(notes: list[dict]) -> None:
    urls = [(f"{SITE_URL}/", notes[0].get("updated") if notes else None), (f"{SITE_URL}/notes/", notes[0].get("updated") if notes else None)]
    urls += [(SITE_URL + note_href(n, from_root=False), n.get("updated")) for n in notes]
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

    inject(
        ROOT / "index.html",
        {
            "latest": render_latest(notes),
            "topics": render_topic_links(notes),
            "stats": f'    <p class="meta-line">{len(notes)} 篇笔记 · 最近更新 {esc(latest)}</p>',
        },
    )
    inject(
        ROOT / "notes" / "index.html",
        {
            "archive": render_archive(notes),
            "tags": render_tag_filters(notes),
            "count": f'    <p class="result-count" data-result-count>{len(notes)} 篇</p>',
        },
    )
    write_feed(notes)
    write_sitemap(notes)
    print(f"已生成：{len(notes)} 篇笔记 · index.html · notes/index.html · feed.xml · sitemap.xml")


if __name__ == "__main__":
    main()
