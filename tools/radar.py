#!/usr/bin/env python3
"""AI 信息雷达：抓取 RSS → 去重 → 打分分类 → （可选）Claude 摘要 → 写入 radar/data/。

用法：
    python3 tools/radar.py                # 抓取并写出今天的数据文件
    python3 tools/radar.py --dry-run      # 只打印结果，不落盘
    RADAR_FIXTURE_DIR=./fixtures python3 tools/radar.py   # 用本地 XML 代替网络请求（测试用）

环境变量：
    ANTHROPIC_API_KEY   有则调用 Claude 做优先级判断和中文摘要（优先）。
    GEMINI_API_KEY      没有 Anthropic key 时改用 Gemini。默认 gemini-pro-latest（最强的 Pro 线），
                        遇到配额或服务错误自动降级到 gemini-flash-latest；可用 GEMINI_MODEL /
                        GEMINI_FALLBACK_MODEL 覆盖。
                        两个都没有则退回关键词规则，每条摘要取原文描述的前 160 字。
    RADAR_WINDOW_HOURS  覆盖 sources.json 里的 window_hours，首次运行或补漏时可以放大到 168。

之后运行 tools/build.py 把数据渲染成页面。
只依赖标准库；anthropic SDK 仅在有 key 时按需导入。
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
RADAR = ROOT / "radar"
DATA = RADAR / "data"
CONFIG = RADAR / "sources.json"
SEEN = DATA / "seen.json"

USER_AGENT = "GarryRadar/1.0 (+https://lgystoic.github.io/radar/)"
FETCH_TIMEOUT = 20
SEEN_RETENTION_DAYS = 120
SUMMARY_FALLBACK_CHARS = 160
CLAUDE_MODEL = "claude-opus-5"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-pro-latest")
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-flash-latest")
LAST_MODEL_USED = ""  # 本次运行实际用到的模型，写进当天数据文件

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# ---------------------------------------------------------------- 工具函数


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def strip_html(text: str) -> str:
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text or "", flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_link(link: str) -> str:
    link = (link or "").strip()
    link = re.sub(r"[?&](utm_[a-z]+|ref|source|fbclid)=[^&#]*", "", link)
    link = re.sub(r"[?&]$", "", link)
    return link.rstrip("/")


def title_key(title: str) -> str:
    """跨源同题去重用：小写、去标点和空白、去掉常见前缀。"""
    t = title.lower()
    t = re.sub(r"^((introducing|announcing|quoting|re:)\s+)+", "", t)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", t)


def item_id(link: str, title: str) -> str:
    key = normalize_link(link).lower() or title.strip().lower()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------- 抓取与解析

def fetch(url: str, source_id: str) -> bytes:
    fixture_dir = os.environ.get("RADAR_FIXTURE_DIR")
    if fixture_dir:
        path = Path(fixture_dir) / f"{source_id}.xml"
        if not path.exists():
            raise FileNotFoundError(f"fixture 缺失：{path}")
        return path.read_bytes()

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        return resp.read()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(el: ET.Element, *names: str) -> str:
    """按本地名取第一个非空子元素文本，忽略命名空间（RSS 1.0 / RDF 会把所有元素放进默认命名空间）。"""
    wanted = {n.lower() for n in names}
    for child in el:
        if _local(child.tag) in wanted:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return ""


def parse_feed(blob: bytes) -> list[dict]:
    """同时支持 RSS 2.0 / RDF(arXiv) / Atom，返回统一的原始条目。"""
    root = ET.fromstring(blob)
    entries: list[dict] = []

    if _local(root.tag) == "feed":  # Atom
        for e in root.iter():
            if _local(e.tag) != "entry":
                continue
            link = ""
            for l in e:
                if _local(l.tag) == "link":
                    rel = l.get("rel", "alternate")
                    if rel == "alternate" or not link:
                        link = l.get("href", "")
            entries.append(
                {
                    "title": _child_text(e, "title"),
                    "link": link,
                    "description": _child_text(e, "summary", "content"),
                    "published": _child_text(e, "published", "updated"),
                }
            )
        return entries

    # RSS 2.0 或 RDF：item 可能在 channel 下，也可能在根下（arXiv 的 RDF）
    for it in root.iter():
        if _local(it.tag) != "item":
            continue
        link = _child_text(it, "link") or it.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", "")
        entries.append(
            {
                "title": _child_text(it, "title"),
                "link": link,
                "description": _child_text(it, "description", "encoded"),
                "published": _child_text(it, "pubDate", "date"),
            }
        )
    return entries


# ---------------------------------------------------------------- 规则打分


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    text = text.lower()
    return [k for k in keywords if k.lower() in text]


def score_item(item: dict, source: dict, rules: dict) -> tuple[int, list[str]]:
    haystack = f"{item['title']} {item['description'][:600]}"
    high = keyword_hits(item["title"], rules["high_keywords"])
    topics = keyword_hits(haystack, rules["topic_keywords"])
    muted = keyword_hits(haystack, rules["mute_keywords"])

    score = int(source.get("weight", 1))
    if high:
        score += 2
    score += min(len(topics), 2)
    if muted:
        score -= 3
    return score, topics[:4]


def priority_from_score(score: int) -> str:
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def fallback_summary(description: str) -> str:
    text = strip_html(description)
    if len(text) <= SUMMARY_FALLBACK_CHARS:
        return text
    cut = text[:SUMMARY_FALLBACK_CHARS]
    # 尽量在句号/空格处截断
    for sep in ("。", ". ", "；", "; ", " "):
        idx = cut.rfind(sep)
        if idx > SUMMARY_FALLBACK_CHARS * 0.6:
            cut = cut[: idx + (1 if sep in "。；" else 0)]
            break
    return cut.rstrip() + "…"


# ---------------------------------------------------------------- Claude 摘要

ENRICH_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    "category": {"type": "string", "enum": ["release", "research", "infra", "people", "industry"]},
                    "summary": {"type": "string"},
                    "why": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "priority", "category", "summary", "why", "tags"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

ENRICH_SYSTEM = """你在为一位做 GPU kernel / 训练性能优化、同时关注生成模型（扩散、Flow Matching、3D/视频生成）的工程师整理每日 AI 信息简报。

对每条输入条目输出：
- priority：high = 真正的模型/权重/重要基础设施发布、榜单显著变化、对他工作有直接影响的技术进展；medium = 值得扫一眼的研究、深度文章、行业动态；low = 泛泛讨论、营销、与他方向无关。
- category：release（模型/产品发布）、research（论文）、infra（GPU/编译器/训练推理系统）、people（个人博客与观点）、industry（行业、融资、政策）。
- summary：一句中文，≤ 60 字，说清「发生了什么」。专有名词、模型名、数字保留原文。
- why：一句中文，≤ 40 字，说清「为什么值得他看」或「为什么可以跳过」。
- tags：2-4 个简短标签，中英文均可。

同一事件被多个源报道时，把最权威的一条标 high，其余标 low 并在 why 里注明「重复」。
不要编造输入里没有的信息。"""


def call_llm_json(system: str, user_msg: str, schema: dict, *, label: str = "llm") -> dict | None:
    """统一入口：有 Anthropic key 用 Claude，否则有 Gemini key 用 Gemini，都没有返回 None。"""
    global LAST_MODEL_USED
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        data = call_claude_json(system, user_msg, schema, label=label)
        if data is not None:
            LAST_MODEL_USED = CLAUDE_MODEL
            return data
    if os.environ.get("GEMINI_API_KEY", "").strip():
        result = call_gemini_json(system, user_msg, schema, label=label)
        if result is not None:
            data, LAST_MODEL_USED = result
            return data
    return None


def _gemini_schema(schema):
    """Gemini 的 responseSchema 是 OpenAPI 子集，不认 additionalProperties。"""
    if isinstance(schema, dict):
        return {k: _gemini_schema(v) for k, v in schema.items() if k != "additionalProperties"}
    if isinstance(schema, list):
        return [_gemini_schema(x) for x in schema]
    return schema


def call_gemini_json(system: str, user_msg: str, schema: dict, *, label: str = "llm") -> tuple[dict, str] | None:
    """先用 GEMINI_MODEL，配额/服务错误时降级到 GEMINI_FALLBACK_MODEL。返回 (数据, 实际模型版本)。"""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    models = [GEMINI_MODEL] + ([GEMINI_FALLBACK_MODEL] if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL else [])
    for i, model in enumerate(models):
        result = _gemini_once(model, api_key, system, user_msg, schema, label=label)
        if result is not None:
            return result
        if i + 1 < len(models):
            log(f"[{label}] 降级到 {models[i + 1]}")
    return None


def _gemini_once(model: str, api_key: str, system: str, user_msg: str, schema: dict, *, label: str) -> tuple[dict, str] | None:
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _gemini_schema(schema),
            "temperature": 0.2,
            "maxOutputTokens": 16384,
        },
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        log(f"[{label}] Gemini {model} HTTP {e.code}：{detail}")
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log(f"[{label}] Gemini {model} 网络错误：{e}")
        return None

    try:
        cand = data["candidates"][0]
        finish = cand.get("finishReason", "")
        text = "".join(part.get("text", "") for part in cand["content"]["parts"])
        parsed = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        log(f"[{label}] Gemini {model} 返回无法解析（{e}；{str(data)[:160]}）")
        return None
    if finish not in ("STOP", ""):
        log(f"[{label}] Gemini {model} finishReason={finish}，输出可能被截断")
        return None
    version = data.get("modelVersion") or model
    usage = data.get("usageMetadata", {})
    log(f"[{label}] Gemini 完成（{version}）：prompt={usage.get('promptTokenCount')} output={usage.get('candidatesTokenCount')} thoughts={usage.get('thoughtsTokenCount')}")
    return parsed, version


def call_claude_json(system: str, user_msg: str, schema: dict, *, label: str = "claude") -> dict | None:
    """Claude 结构化输出调用。任何失败都返回 None，让调用方退回规则；绝不让整次运行挂掉。"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        log(f"[{label}] 检测到 ANTHROPIC_API_KEY 但未安装 anthropic SDK（pip install anthropic），退回规则模式")
        return None

    client = anthropic.Anthropic()
    request = dict(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
    )
    try:
        try:
            # 首选：带服务端 refusal fallback 的 beta 端点
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request
            )
        except anthropic.BadRequestError as e:
            log(f"[{label}] beta 端点被拒（{e.message}），改用标准端点重试")
            response = client.messages.create(**request)
    except anthropic.AuthenticationError:
        log(f"[{label}] ANTHROPIC_API_KEY 无效，退回规则模式")
        return None
    except anthropic.RateLimitError as e:
        log(f"[{label}] 触发限流：{e.message}，退回规则模式")
        return None
    except anthropic.APIStatusError as e:
        log(f"[{label}] API 错误 {e.status_code}：{e.message}，退回规则模式")
        return None
    except anthropic.APIConnectionError as e:
        log(f"[{label}] 网络错误：{e}，退回规则模式")
        return None

    if response.stop_reason == "refusal":
        detail = getattr(response, "stop_details", None)
        log(f"[{label}] 模型拒绝了请求（{getattr(detail, 'category', None)}），退回规则模式")
        return None

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log(f"[{label}] 模型返回的不是合法 JSON，退回规则模式")
        return None

    usage = getattr(response, "usage", None)
    if usage:
        log(f"[{label}] Claude 完成：input={usage.input_tokens} output={usage.output_tokens}")
    return data


def ai_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip())


def enrich_with_ai(items: list[dict]) -> dict[str, dict] | None:
    """返回 {id: {priority, category, summary, why, tags}}；失败返回 None 让调用方退回规则。"""
    if not ai_available():
        return None
    payload = [
        {
            "id": it["id"],
            "source": it["source"],
            "title": it["title"],
            "published": it["published"],
            "excerpt": strip_html(it["description"])[:700],
            "rule_priority": it["priority"],
        }
        for it in items
    ]
    user_msg = "以下是过去一天抓到的条目（JSON）。请按系统说明逐条给出 priority / category / summary / why / tags：\n\n" + json.dumps(payload, ensure_ascii=False)
    data = call_llm_json(ENRICH_SYSTEM, user_msg, ENRICH_SCHEMA, label="radar")
    if not data:
        return None
    return {row["id"]: row for row in data.get("items", []) if "id" in row}


# ---------------------------------------------------------------- 主流程


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def collect(config: dict, now_utc: datetime, seen: dict[str, str]) -> tuple[list[dict], list[dict]]:
    rules = config["rules"]
    window_hours = int(os.environ.get("RADAR_WINDOW_HOURS") or config["site"].get("window_hours", 36))
    window = timedelta(hours=window_hours)
    log(f"[radar] 时间窗口 {window_hours} 小时")
    items: dict[str, dict] = {}
    status: list[dict] = []

    for source in config["sources"]:
        sid = source["id"]
        try:
            blob = fetch(source["url"], sid)
            raw_entries = parse_feed(blob)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ET.ParseError, FileNotFoundError, OSError) as e:
            status.append({"id": sid, "name": source["name"], "ok": False, "count": 0, "error": str(e)[:160]})
            log(f"[radar] ✗ {source['name']}: {e}")
            continue

        kept = 0
        for raw in raw_entries:
            title = strip_html(raw["title"])
            link = raw["link"].strip()
            if not title or not link:
                continue
            iid = item_id(link, title)
            if iid in seen or iid in items:
                continue
            published = parse_date(raw["published"])
            if published and now_utc - published > window:
                continue

            item = {
                "id": iid,
                "title": title,
                "link": normalize_link(link) or link,
                "source": source["name"],
                "source_id": sid,
                "category": source.get("category", "industry"),
                "published": published.isoformat() if published else "",
                "description": raw["description"],
            }
            score, topics = score_item(item, source, rules)
            if source.get("require_topic") and not topics:
                continue
            item["score"] = score
            item["priority"] = priority_from_score(score)
            item["tags"] = topics
            items[iid] = item
            kept += 1

        status.append({"id": sid, "name": source["name"], "ok": True, "count": kept, "error": ""})
        log(f"[radar] ✓ {source['name']}: {kept} 条新内容（共 {len(raw_entries)} 条）")

    return dedupe_titles(list(items.values()), config), status


def dedupe_titles(items: list[dict], config: dict) -> list[dict]:
    """同一标题被多个源转载时只保留权重最高的一条（同权重取更早发布的）。"""
    weight = {s["id"]: int(s.get("weight", 1)) for s in config["sources"]}
    best: dict[str, dict] = {}
    for it in items:
        key = title_key(it["title"])
        if len(key) < 8:  # 标题太短没法判定同题，直接保留
            key = it["id"]
        cur = best.get(key)
        if cur is None or (weight.get(it["source_id"], 1), it["published"] or "9") > (weight.get(cur["source_id"], 1), cur["published"] or "9"):
            if cur is not None:
                log(f"[radar] 同题去重：保留 {it['source']}，丢弃 {cur['source']} ← {it['title'][:50]}")
            best[key] = it
        else:
            log(f"[radar] 同题去重：保留 {cur['source']}，丢弃 {it['source']} ← {it['title'][:50]}")
    return list(best.values())


def finalize(items: list[dict], enrichment: dict[str, dict] | None) -> list[dict]:
    out = []
    for it in items:
        row = {
            "id": it["id"],
            "title": it["title"],
            "link": it["link"],
            "source": it["source"],
            "source_id": it["source_id"],
            "published": it["published"],
            "category": it["category"],
            "priority": it["priority"],
            "summary": fallback_summary(it["description"]),
            "why": "",
            "tags": it["tags"],
        }
        if enrichment and it["id"] in enrichment:
            e = enrichment[it["id"]]
            row.update(
                priority=e.get("priority", row["priority"]),
                category=e.get("category", row["category"]),
                summary=e.get("summary") or row["summary"],
                why=e.get("why", ""),
                tags=(e.get("tags") or row["tags"])[:4],
            )
        out.append(row)

    return sort_rows(out)


def sort_rows(rows: list[dict]) -> list[dict]:
    """优先级升序（high 在前），同一优先级内按发布时间倒序。"""
    rows.sort(key=lambda r: r["published"] or "", reverse=True)
    rows.sort(key=lambda r: PRIORITY_ORDER[r["priority"]])
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    ap.add_argument("--date", help="覆盖日期标签（YYYY-MM-DD），默认取配置时区的今天")
    args = ap.parse_args()

    config = load_json(CONFIG, None)
    if not config:
        raise SystemExit(f"缺少配置文件 {CONFIG}")

    tz = ZoneInfo(config["site"].get("timezone", "Asia/Shanghai"))
    now_utc = datetime.now(timezone.utc)
    today = args.date or now_utc.astimezone(tz).strftime("%Y-%m-%d")

    seen: dict[str, str] = load_json(SEEN, {})
    day_path = DATA / f"{today}.json"
    existing = load_json(day_path, None)
    # 同一天重复运行：已经写进今天文件的条目允许再次出现，避免覆盖丢失
    if existing:
        for row in existing.get("items", []):
            seen.pop(row["id"], None)

    items, status = collect(config, now_utc, seen)
    log(f"[radar] 共 {len(items)} 条新内容，来自 {sum(1 for s in status if s['ok'])}/{len(status)} 个源")

    # 当天文件是规则模式生成的、而这次有 AI 可用：把旧条目一起重新过一遍，整期升级成 AI 版
    if existing and not existing.get("ai") and ai_available() and existing.get("items"):
        known = {it["id"] for it in items}
        for row in existing["items"]:
            if row["id"] in known:
                continue
            items.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "link": row["link"],
                    "source": row["source"],
                    "source_id": row.get("source_id", ""),
                    "category": row.get("category", "industry"),
                    "published": row.get("published", ""),
                    "description": row.get("summary", ""),
                    "score": 0,
                    "priority": row.get("priority", "low"),
                    "tags": row.get("tags", []),
                }
            )
        log(f"[radar] 当天已有 {len(existing['items'])} 条规则版条目，本次连同新内容一起交给 AI 重排")
        existing = None

    enrichment = enrich_with_ai(items) if items else None
    rows = finalize(items, enrichment)

    if existing:
        known = {r["id"] for r in rows}
        rows.extend(r for r in existing.get("items", []) if r["id"] not in known)
        rows = sort_rows(rows)

    day = {
        "date": today,
        "generated_at": now_utc.isoformat(timespec="seconds"),
        "ai": bool(enrichment),
        "model": LAST_MODEL_USED if enrichment else "",
        "sources": status,
        "counts": {p: sum(1 for r in rows if r["priority"] == p) for p in ("high", "medium", "low")},
        "items": rows,
    }

    if args.dry_run:
        print(json.dumps(day, ensure_ascii=False, indent=2))
        return

    DATA.mkdir(parents=True, exist_ok=True)
    day_path.write_text(json.dumps(day, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 更新已见集合并清理过期记录
    cutoff = (now_utc - timedelta(days=SEEN_RETENTION_DAYS)).strftime("%Y-%m-%d")
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    for r in rows:
        seen[r["id"]] = today
    SEEN.write_text(json.dumps(seen, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    log(f"[radar] 已写入 {day_path.relative_to(ROOT)}：high={day['counts']['high']} medium={day['counts']['medium']} low={day['counts']['low']}")


if __name__ == "__main__":
    main()
