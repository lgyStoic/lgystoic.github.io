#!/usr/bin/env python3
"""活动雷达：从活动源里找出可以报名参加的东西，抽出日期/地点/费用/截止，维护一份「即将发生」清单。

用法：
    python3 tools/events.py            # 抓取 → 去重 → 抽取 → 更新 radar/data/events.json
    python3 tools/events.py --dry-run  # 只打印

源类型（radar/event_sources.json）：
    rss / json   复用 radar.py 的解析
    ics          iCal 日历（lu.ma 日历、Google 日历公开订阅）
    page         静态列表页：按 link_pattern 抽链接，再逐个抓详情页的 OG / JSON-LD Event
    yaml         ai-deadlines 那种 "- key: value" 扁平列表

有 GEMINI_API_KEY / ANTHROPIC_API_KEY 时由模型判断是否为活动并抽结构化字段；没有时用源的默认值。
之后运行 tools/build.py 渲染 /radar/events/。
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import radar  # noqa: E402
from radar import call_llm_json, fetch, item_id, log, normalize_link, parse_date, parse_feed, parse_json_feed, strip_html  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "radar" / "event_sources.json"
DATA = ROOT / "radar" / "data" / "events.json"
TZ = ZoneInfo("Asia/Shanghai")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

TYPES = ("meetup", "hackathon", "competition", "talk", "conference", "deadline", "other")


# ---------------------------------------------------------------- 解析器


def _unfold_ics(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw.rstrip("\r"))
    return lines


def _ics_date(value: str) -> str:
    """20260920T100000Z / 20260920 → YYYY-MM-DD（按上海时区）。"""
    value = value.strip()
    try:
        if "T" in value:
            dt = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
            if value.endswith("Z"):
                dt = dt.replace(tzinfo=timezone.utc).astimezone(TZ)
            return dt.strftime("%Y-%m-%d")
        return datetime.strptime(value[:8], "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def parse_ics(blob: bytes) -> list[dict]:
    entries, cur = [], None
    for line in _unfold_ics(blob.decode("utf-8", "replace")):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT" and cur is not None:
            title = cur.get("SUMMARY", "")
            link = cur.get("URL", "") or cur.get("UID", "")
            if title:
                entries.append(
                    {
                        "title": title,
                        "link": link,
                        "description": cur.get("DESCRIPTION", "").replace("\\n", " ").replace("\\,", ","),
                        "published": "",
                        "hints": {
                            "start": _ics_date(cur.get("DTSTART", "")),
                            "end": _ics_date(cur.get("DTEND", "")),
                            "location": cur.get("LOCATION", "").replace("\\,", ","),
                        },
                    }
                )
            cur = None
        elif cur is not None and ":" in line:
            key, value = line.split(":", 1)
            key = key.split(";", 1)[0].upper()
            cur[key] = value
    return entries


def parse_yaml_list(blob: bytes) -> list[dict]:
    """只认 ai-deadlines 这种扁平 '- key: value' 列表，不是通用 YAML。"""
    items, cur = [], None
    for raw in blob.decode("utf-8", "replace").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith("- "):
            cur = {}
            items.append(cur)
            line = "  " + line[2:]
        if cur is None or ":" not in line:
            continue
        key, value = line.strip().split(":", 1)
        cur[key.strip()] = value.strip().strip("'\"")
    entries = []
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    for it in items:
        deadline = (it.get("deadline") or "")[:10]
        title = it.get("title") or it.get("id", "")
        if not title or not deadline or deadline.upper() == "TBA" or deadline < today:
            continue
        entries.append(
            {
                "title": f"{title} {it.get('year', '')} 投稿截止".strip(),
                "link": it.get("link", "") or f"https://aideadlin.es/?sub={it.get('sub', '')}#{it.get('id', '')}",
                "description": f"{it.get('full_name', '')}. 会议时间 {it.get('date', '')}，地点 {it.get('place', '')}。截止 {it.get('deadline', '')} ({it.get('timezone', '')})",
                "published": "",
                "hints": {"deadline": deadline, "start": deadline, "location": it.get("place", "")},
            }
        )
    return entries


ANCHOR_RE = re.compile(r"<a\b[^>]*?href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)


def parse_page(blob: bytes, source: dict) -> list[dict]:
    html = blob.decode("utf-8", "replace")
    pattern = re.compile(source["link_pattern"])
    exclude = re.compile(source["exclude_pattern"]) if source.get("exclude_pattern") else None
    base = source.get("base") or source["url"]
    seen, entries = set(), []
    for m in ANCHOR_RE.finditer(html):
        href, inner = m.group(1), m.group(2)
        # href 里常见 &amp; 转义和跟踪参数；列表页链接的 query 一律不要
        url = urljoin(base, html_mod.unescape(href.strip()))
        url = normalize_link(url.split("#", 1)[0].split("?", 1)[0])
        if not pattern.search(url) or url in seen or (exclude and exclude.search(url)):
            continue
        seen.add(url)
        # 列表页上链接前后的文字通常就是日期、地点、价格——详情页可能是前端渲染拿不到，这里先兜住
        context = strip_html(html[max(0, m.start() - 250) : m.end() + 450])
        entries.append({"title": strip_html(inner)[:200], "link": url, "description": context[:600], "published": "", "hints": {}})
    return entries


# ---------------------------------------------------------------- 详情页


def fetch_detail(url: str) -> dict:
    """抓活动详情页的 OG 与 schema.org Event（有的话直接拿到时间地点）。fixture 模式跳过。"""
    if os.environ.get("RADAR_FIXTURE_DIR"):
        return {}
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read(400_000).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        log(f"[events] 详情页取不到 {url[:70]}：{e}")
        return {}

    def meta(*names: str) -> str:
        for n in names:
            for pat in (
                rf'<meta[^>]+(?:property|name)=["\']{re.escape(n)}["\'][^>]+content=["\']([^"\']*)["\']',
                rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{re.escape(n)}["\']',
            ):
                m = re.search(pat, html, re.I)
                if m and m.group(1).strip():
                    return strip_html(m.group(1))
        return ""

    out = {"title": meta("og:title", "twitter:title"), "description": meta("og:description", "description")[:600], "hints": {}}
    if not out["title"]:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        out["title"] = strip_html(m.group(1)) if m else ""
    # 正文前 1200 字：日期、地点、费用往往只在正文里，OG 描述放不下
    body = re.search(r"<body[^>]*>(.*)</body>", html, re.I | re.S)
    body_text = strip_html(re.sub(r"<(nav|header|footer|script|style)\b.*?</\1>", " ", body.group(1) if body else html, flags=re.I | re.S))
    out["text"] = body_text[:1200]

    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if "@graph" in node and isinstance(node["@graph"], list):
                nodes.extend(n for n in node["@graph"] if isinstance(n, dict))
            if str(node.get("@type", "")).endswith("Event"):
                loc = node.get("location") or {}
                if isinstance(loc, list):
                    loc = loc[0] if loc else {}
                addr = loc.get("address") if isinstance(loc, dict) else ""
                if isinstance(addr, dict):
                    addr = " ".join(str(addr.get(k, "")) for k in ("addressLocality", "addressRegion", "streetAddress") if addr.get(k))
                out["hints"] = {
                    "start": str(node.get("startDate", ""))[:10],
                    "end": str(node.get("endDate", ""))[:10],
                    "location": " ".join(x for x in [str(loc.get("name", "")) if isinstance(loc, dict) else "", str(addr or "")] if x).strip(),
                    "online": "Online" in str(node.get("eventAttendanceMode", "")),
                    "organizer": (node.get("organizer") or {}).get("name", "") if isinstance(node.get("organizer"), dict) else "",
                }
                if not out["description"]:
                    out["description"] = strip_html(str(node.get("description", "")))[:600]
                break
    return out


# ---------------------------------------------------------------- AI 抽取

EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "is_event": {"type": "boolean"},
                    "title": {"type": "string"},
                    "event_type": {"type": "string", "enum": list(TYPES)},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "deadline": {"type": "string"},
                    "city": {"type": "string"},
                    "online": {"type": "boolean"},
                    "fee": {"type": "string"},
                    "organizer": {"type": "string"},
                    "summary": {"type": "string"},
                    "relevance": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["id", "is_event", "title", "event_type", "start", "end", "deadline", "city", "online", "fee", "organizer", "summary", "relevance"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

EVENT_SYSTEM = """你在为一位住在深圳、做 GPU kernel 与训练性能优化、关注生成模型的工程师整理「可以报名参加的活动」清单。他现在时间比较多，想主动发现值得去的线下聚会、黑客松、比赛、讲座、大会，以及学术会议的投稿截止。

对每条输入判断并抽取：
- is_event：这是不是一个有具体时间、可以参加/报名/投稿的活动？新闻报道、产品发布、招聘、课程广告、已结束的活动 → false。
- title：≤ 30 字中文标题（保留活动名中的英文专名）。
- event_type：meetup（线下聚会）/ hackathon / competition（数据或算法比赛）/ talk（讲座、沙龙、分享会）/ conference（大会、峰会）/ deadline（学术会议投稿截止）/ other。
- start / end：活动日期，YYYY-MM-DD；多天填 start 和 end；不确定留空。比赛类 start 填报名开始或当前日期均可留空，deadline 更重要。
- deadline：报名 / 提交 / 投稿截止日期，YYYY-MM-DD；没有留空。
- city：城市中文名（深圳 / 广州 / 香港 / 北京 / 上海 / 杭州 …）；纯线上填「线上」；不确定填「」。
- online：是否可以线上参加。
- fee：费用，如「免费」「¥99」「$50」；不确定留空。
- organizer：主办方，≤ 20 字；不确定留空。
- summary：≤ 60 字，说清这是什么、适合谁。只能用输入里的信息。
- relevance：high = 深圳/广州/香港线下或线上、且和 AI / GPU / 生成模型 / 系统性能相关；medium = 相关但在其他城市，或本地但主题一般相关；low = 主题无关或明显不适合他。

日期只在输入里有明确依据时填写，今天的日期会在用户消息里给出，用它把「本周六」「下周」这类相对表述换算成具体日期。不要编造。"""


def enrich_events(cands: list[dict], today: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(cands), 30):
        batch = cands[i : i + 30]
        payload = [
            {
                "id": c["id"],
                "source": c["source"],
                "default_type": c["default_type"],
                "default_city": c["default_city"],
                "title": c["title"],
                "description": strip_html(c["description"])[:900],
                "hints": {k: v for k, v in (c.get("hints") or {}).items() if v},
                "url": c["link"],
            }
            for c in batch
        ]
        data = call_llm_json(EVENT_SYSTEM, f"今天是 {today}（北京时间）。候选条目（JSON）：\n\n" + json.dumps(payload, ensure_ascii=False), EVENT_SCHEMA, label="events")
        if not data:
            log(f"[events] 第 {i // 30 + 1} 批 AI 抽取失败，这批用默认值")
            continue
        for row in data.get("items", []):
            if "id" in row:
                out[row["id"]] = row
    return out


# ---------------------------------------------------------------- 主流程


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def valid_date(value: str) -> str:
    value = (value or "").strip()[:10]
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        return ""


def sort_key(ev: dict) -> tuple:
    return (ev.get("start") or ev.get("deadline") or "9999-12-31", ev.get("title", ""))


def collect(config: dict, seen: dict) -> tuple[list[dict], list[dict]]:
    site = config["site"]
    per_source = site.get("max_candidates_per_source", 40)
    cands: dict[str, dict] = {}
    status: list[dict] = []
    for source in config["sources"]:
        sid, kind = source["id"], source.get("kind", "rss")
        try:
            blob = fetch(source["url"], sid)
            if kind == "ics":
                entries = parse_ics(blob)
            elif kind == "page":
                entries = parse_page(blob, source)
            elif kind == "yaml":
                entries = parse_yaml_list(blob)
            elif kind == "json":
                entries = parse_json_feed(blob, source)
            else:
                entries = parse_feed(blob)
        except Exception as e:  # 任何一个源坏掉都不该拖垮整轮
            status.append({"id": sid, "name": source["name"], "ok": False, "count": 0, "error": str(e)[:160]})
            log(f"[events] ✗ {source['name']}: {e}")
            continue

        kept = 0
        for raw in entries[:per_source]:
            link = normalize_link(raw.get("link", "")) or raw.get("link", "")
            title = strip_html(raw.get("title", ""))
            if not link:
                continue
            cid = item_id(link, title)
            if cid in seen or cid in cands:
                continue
            if kind == "rss":
                published = parse_date(raw.get("published"))
                if published and datetime.now(timezone.utc) - published > timedelta(days=10):
                    continue
            cands[cid] = {
                "id": cid,
                "title": title,
                "link": link,
                "description": raw.get("description", ""),
                "hints": raw.get("hints", {}) or {},
                "source": source["name"],
                "source_id": sid,
                "default_type": source.get("default_type", "other"),
                "default_city": source.get("default_city", ""),
                "kind": kind,
            }
            kept += 1
        status.append({"id": sid, "name": source["name"], "ok": True, "count": kept, "error": ""})
        log(f"[events] ✓ {source['name']}: {kept} 条新候选（共 {len(entries)} 条）")
    return list(cands.values()), status


def to_event(c: dict, ai: dict | None, today: str) -> dict | None:
    hints = c.get("hints") or {}
    detail = c.get("detail") or {}
    dh = detail.get("hints") or {}
    ev = {
        "id": c["id"],
        "title": (ai or {}).get("title") or detail.get("title") or c["title"] or c["link"],
        "link": c["link"],
        "source": c["source"],
        "source_id": c["source_id"],
        "found": today,
        "event_type": (ai or {}).get("event_type") or c["default_type"],
        "start": valid_date((ai or {}).get("start") or dh.get("start") or hints.get("start") or ""),
        "end": valid_date((ai or {}).get("end") or dh.get("end") or hints.get("end") or ""),
        "deadline": valid_date((ai or {}).get("deadline") or hints.get("deadline") or ""),
        "city": (ai or {}).get("city") or dh.get("location") or hints.get("location") or c["default_city"],
        "online": bool((ai or {}).get("online", dh.get("online", c["default_city"] == "线上"))),
        "fee": (ai or {}).get("fee", ""),
        "organizer": (ai or {}).get("organizer") or dh.get("organizer", ""),
        "summary": (ai or {}).get("summary") or strip_html(detail.get("description") or c["description"])[:160],
        "relevance": (ai or {}).get("relevance", "medium"),
        "ai": bool(ai),
    }
    if ai is not None and not ai.get("is_event", True):
        return None
    if ev["event_type"] not in TYPES:
        ev["event_type"] = "other"
    return ev


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--date", help="覆盖今天的日期（测试用）")
    args = ap.parse_args()

    config = load_json(CONFIG, None)
    if not config:
        raise SystemExit(f"缺少 {CONFIG}")
    site = config["site"]
    today = args.date or datetime.now(TZ).strftime("%Y-%m-%d")

    data = load_json(DATA, {"events": [], "seen": {}, "sources": [], "updated": ""})
    seen: dict[str, str] = data.get("seen", {})

    cands, status = collect(config, seen)
    cands = cands[: site.get("max_new_per_run", 120)]
    log(f"[events] 共 {len(cands)} 条新候选，来自 {sum(1 for s in status if s['ok'])}/{len(status)} 个源")

    # page 源的链接只有标题甚至没有标题，抓一下详情页
    budget = site.get("max_detail_fetch", 40)
    for c in cands:
        if c["kind"] == "page" and budget > 0:
            c["detail"] = fetch_detail(c["link"])
            budget -= 1
            if c["detail"].get("title") and not c["title"]:
                c["title"] = c["detail"]["title"]
            desc = c["detail"].get("description", "")
            text = c["detail"].get("text", "")
            # 列表页上下文 + OG 描述 + 正文前段，一起给模型抽日期/地点
            c["description"] = "\n".join(x for x in (c["description"], desc, text if len(desc) < 200 else "") if x)

    # 同一个源里 3 条以上共用同一个标题，多半是前端渲染页的占位标题（如「算法大赛-天池大赛」），没有信息量
    from collections import Counter
    dup = Counter((c["source_id"], c["title"]) for c in cands if c["title"])
    before = len(cands)
    cands = [c for c in cands if dup[(c["source_id"], c["title"])] < 3]
    if len(cands) != before:
        log(f"[events] 丢弃 {before - len(cands)} 条占位标题候选")

    # 源从配置里移除后，它留下的旧条目一起清掉（例如被证实是前端渲染占位页的源）
    live_sources = {s["id"] for s in config["sources"]} | {"inbox"}
    events = {e["id"]: e for e in data.get("events", []) if e.get("source_id") in live_sources}

    # 自愈：已入库但没抽到日期的活动，补抓一次详情页正文再重抽（每轮最多 15 条，只补一次）
    src_by_id = {s["id"]: s for s in config["sources"]}
    undated = [ev for ev in events.values() if not ev.get("start") and not ev.get("deadline") and not ev.get("refreshed")][:15]
    if undated and radar.ai_available():
        for ev in undated:  # 重抽有自己的预算，不和新候选抢
            ev["refreshed"] = True
            detail = fetch_detail(ev["link"])
            desc = detail.get("description", "")
            text = detail.get("text", "")
            src = src_by_id.get(ev.get("source_id"), {})
            cands.append(
                {
                    "id": ev["id"], "title": ev["title"], "link": ev["link"],
                    "description": (desc + "\n" + text) if text else (desc or ev.get("summary", "")),
                    "hints": detail.get("hints") or {},
                    "source": ev["source"], "source_id": ev.get("source_id", ""),
                    "default_type": ev.get("event_type") or src.get("default_type", "other"),
                    "default_city": ev.get("city") or src.get("default_city", ""),
                    "kind": "refresh", "detail": detail, "_existing": ev,
                }
            )
        log(f"[events] 重抽 {len(undated)} 条没有日期的旧活动")

    ai = enrich_events(cands, today) if cands and radar.ai_available() else {}
    model = radar.LAST_MODEL_USED if ai else ""
    if len(events) != len(data.get("events", [])):
        log(f"[events] 清掉 {len(data.get('events', [])) - len(events)} 条已移除源的旧条目")
    added, dropped = 0, 0
    for c in cands:
        ev = to_event(c, ai.get(c["id"]) if ai else None, today)
        seen[c["id"]] = today
        if c.get("kind") == "refresh":
            old = c["_existing"]
            if ev is None:
                events.pop(old["id"], None)  # 重看之后判定不是活动，删掉
                dropped += 1
            else:
                ev["found"] = old.get("found", today)
                ev["refreshed"] = True
                events[old["id"]] = ev
            continue
        if ev is None:
            dropped += 1
            continue
        events[ev["id"]] = ev
        added += 1

    # 清理：结束（或截止）超过 keep_past_days 的活动；seen 保留 180 天
    cutoff = (datetime.now(TZ) - timedelta(days=site.get("keep_past_days", 14))).strftime("%Y-%m-%d")
    kept = []
    for ev in events.values():
        last = ev.get("end") or ev.get("start") or ev.get("deadline") or ev.get("found")
        if last and last < cutoff:
            continue
        kept.append(ev)
    kept.sort(key=sort_key)
    seen_cutoff = (datetime.now(TZ) - timedelta(days=180)).strftime("%Y-%m-%d")
    seen = {k: v for k, v in seen.items() if v >= seen_cutoff}

    out = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "today": today,
        "model": model,
        "sources": status,
        "events": kept,
        "seen": seen,
    }
    log(f"[events] 新增 {added}，判定非活动丢弃 {dropped}，清单共 {len(kept)} 条，模型 {model or '规则'}")
    if args.dry_run:
        print(json.dumps({k: v for k, v in out.items() if k != "seen"}, ensure_ascii=False, indent=2))
        return
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
