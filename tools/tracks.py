#!/usr/bin/env python3
"""专题追踪：把每日雷达里带 tracks 标签的条目累积成每个专题的时间线，按主体（模型 / 产品）串成线程，
每周让模型写一段综述并维护「现状表」。输出 radar/data/tracks/<id>.json，页面由 build.py 生成。

流程（radar.yml 里跟在雷达之后）：
  1. 读 radar/tracks.json 与所有 radar/data/<日期>.json，收集 tracks 非空的条目
  2. 新条目批量交给模型抽 entity（规范主体名，如 Wan2.6、Genie 3）与 kind；无 key 时用标题里的首个专名兜底
  3. 距上次综述 ≥ 6 天且近 7 天有 ≥ 3 条新内容 → 模型写 digest（这周变了什么）并更新 sota 表
  4. 写回 radar/data/tracks/<id>.json（公开数据，不放任何密钥）

用法：python3 tools/tracks.py            # 全部专题
      TRACKS_FORCE_DIGEST=1 python3 tools/tracks.py   # 强制重写综述
"""
import json, os, re, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import radar
from radar import call_llm_json, log, load_tracks, match_tracks

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "radar" / "data"
OUT = DATA / "tracks"
KEEP_DAYS = 180

ENTITY_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
    "id": {"type": "string"}, "entity": {"type": "string"}, "kind": {"type": "string", "enum": ["release", "paper", "benchmark", "tool", "news", "opinion"]}},
    "required": ["id", "entity", "kind"], "additionalProperties": False}}}, "required": ["items"], "additionalProperties": False}
ENTITY_SYSTEM = """你在整理一个技术专题的时间线。对每条输入给出：
- entity：这条内容的主体，用规范短名：模型/产品名带版本（如 "Wan2.6"、"Genie 3"、"Veo 3.1"、"Cosmos-Predict2"、"HunyuanVideo-1.5"），论文用方法名或模型名，工具用仓库名；说不出具体主体就写所属机构（如 "Google DeepMind"）；无法判断写 ""。同一主体在不同条目里必须写成完全一样的字符串。
- kind：release（模型/权重/产品发布）、paper（论文）、benchmark（评测榜单）、tool（推理框架/工具支持）、news（新闻/融资/合作）、opinion（观点/教程）。
只用输入里的信息，不要联想。"""

DIGEST_SCHEMA = {"type": "object", "properties": {
    "digest": {"type": "string"},
    "highlights": {"type": "array", "items": {"type": "string"}},
    "sota": {"type": "array", "items": {"type": "object", "properties": {
        "model": {"type": "string"}, "org": {"type": "string"}, "date": {"type": "string"}, "open_weights": {"type": "boolean"},
        "spec": {"type": "string"}, "link": {"type": "string"}, "note": {"type": "string"}},
        "required": ["model", "org", "date", "open_weights", "spec", "link", "note"], "additionalProperties": False}}},
    "required": ["digest", "highlights", "sota"], "additionalProperties": False}
DIGEST_SYSTEM = """你在维护一个技术专题页（读者：做生成模型推理加速的工程师）。输入是这个专题最近 7 天的新条目、之前 30 天的条目摘要，以及上一版「现状表」。请输出：
- digest：本周综述，150–300 字中文，说清这周发生了什么、哪些是真正的进展、哪些只是噱头；只用输入里的事实，不补充你记忆里的模型。
- highlights：3–5 条，每条 ≤40 字，本周最值得看的进展。
- sota：更新后的现状表（≤12 行）：当前值得知道的主要模型/系统，每行 model / org / date（首次发布或最近大版本，YYYY-MM-DD 或 YYYY-MM）/ open_weights / spec（一句话：分辩率、时长、参数量、架构等已知信息，不知道写 "—"）/ link（输入里有的链接，没有写 ""）/ note（≤30 字，和同类比的位置）。在上一版基础上增删改：新条目里出现的新模型加进去，被明显超越或过时的删掉，保持按重要性排序。不要编造日期和规格，输入没有就写 "—"。"""


def now_utc():
    return datetime.now(timezone.utc)


def load_days() -> list[dict]:
    days = []
    for p in sorted(DATA.glob("20??-??-??.json"), reverse=True):
        try:
            days.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return days


def fallback_entity(title: str) -> str:
    """无模型时的兜底：标题里第一个「大写开头 + 可带版本号」的专名。"""
    m = re.search(r"\b([A-Z][A-Za-z0-9]+(?:[-. ][A-Za-z0-9]+){0,2}(?:\s?\d+(?:\.\d+)?)?)", title)
    return m.group(1).strip() if m else ""


def extract_entities(entries: list[dict]) -> None:
    """就地填 entity / kind；模型不可用时用兜底。"""
    todo = [e for e in entries if e.get("entity") is None]
    if not todo:
        return
    for i in range(0, len(todo), 40):
        batch = todo[i:i + 40]
        prompt = json.dumps([{"id": e["id"], "title": e["title"], "summary": e.get("summary", "")[:160], "source": e.get("source", "")} for e in batch], ensure_ascii=False)
        result = call_llm_json(ENTITY_SYSTEM, prompt, ENTITY_SCHEMA, label="tracks") or {}
        got = {r["id"]: r for r in result.get("items", []) if r.get("id")}
        for e in batch:
            r = got.get(e["id"])
            e["entity"] = (r or {}).get("entity", "").strip() if r else fallback_entity(e["title"])
            e["kind"] = (r or {}).get("kind", "news") if r else "news"


def need_digest(state: dict, entries: list[dict], today: datetime) -> bool:
    if os.environ.get("TRACKS_FORCE_DIGEST") == "1":
        return True
    last = (state.get("digest") or {}).get("generated_at", "")
    if last:
        try:
            if today - datetime.fromisoformat(last) < timedelta(days=6):
                return False
        except ValueError:
            pass
    week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    return sum(1 for e in entries if e["date"] >= week_ago) >= 3


def write_digest(track: dict, state: dict, entries: list[dict], today: datetime) -> None:
    week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    month_ago = (today - timedelta(days=37)).strftime("%Y-%m-%d")
    recent = [e for e in entries if e["date"] >= week_ago]
    older = [e for e in entries if month_ago <= e["date"] < week_ago]
    prompt = json.dumps({
        "track": track["name"], "week": f"{week_ago} ~ {today.strftime('%Y-%m-%d')}",
        "new_entries": [{"date": e["date"], "entity": e.get("entity", ""), "kind": e.get("kind", ""), "title": e["title"], "summary": e.get("summary", ""), "link": e["link"]} for e in recent[:60]],
        "older_entries": [{"date": e["date"], "entity": e.get("entity", ""), "title": e["title"]} for e in older[:80]],
        "previous_sota": state.get("sota", []),
    }, ensure_ascii=False)
    result = call_llm_json(DIGEST_SYSTEM, prompt, DIGEST_SCHEMA, label=f"tracks-{track['id']}")
    if not result:
        log(f"[tracks] {track['name']}：综述未生成（模型不可用），保留上一版")
        return
    state["digest"] = {"text": result.get("digest", "").strip(), "highlights": [h.strip() for h in result.get("highlights", []) if h.strip()][:5],
                       "week": f"{week_ago} ~ {today.strftime('%Y-%m-%d')}", "generated_at": today.isoformat(timespec="seconds"), "model": radar.LAST_MODEL_USED}
    sota = [r for r in result.get("sota", []) if r.get("model")][:12]
    if sota:
        state["sota"] = sota
    log(f"[tracks] {track['name']}：综述已更新，现状表 {len(state.get('sota', []))} 行")


def build_track(track: dict, days: list[dict], today: datetime) -> dict:
    path = OUT / f"{track['id']}.json"
    state = {}
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
    known = {e["id"]: e for e in state.get("entries", [])}
    cutoff = (today - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    entries: dict[str, dict] = {k: v for k, v in known.items() if v.get("date", "") >= cutoff}
    added = 0
    for day in days:
        for row in day.get("items", []):
            row_tracks = row.get("tracks")
            if row_tracks is None:  # 专题功能上线前的旧数据：用标题 + 摘要补打标签
                row_tracks = match_tracks({"title": row.get("title", ""), "description": row.get("summary", "")}, {}, [track])
            if track["id"] not in row_tracks or row["id"] in entries or day["date"] < cutoff:
                continue
            entries[row["id"]] = {"id": row["id"], "date": day["date"], "title": row["title"], "link": row["link"], "source": row.get("source", ""),
                                  "priority": row.get("priority", "low"), "summary": row.get("summary", ""), "why": row.get("why", ""),
                                  "tags": row.get("tags", [])[:4], "entity": None, "kind": None}
            added += 1
    ordered = sorted(entries.values(), key=lambda e: (e["date"], e.get("priority") == "high"), reverse=True)
    extract_entities(ordered)
    state.update({"id": track["id"], "name": track["name"], "blurb": track.get("blurb", ""), "updated": today.isoformat(timespec="seconds"), "entries": ordered})
    if need_digest(state, ordered, today):
        write_digest(track, state, ordered, today)
    threads: dict[str, list[str]] = {}
    for e in ordered:
        if e.get("entity"):
            threads.setdefault(e["entity"], []).append(e["id"])
    state["threads"] = dict(sorted(threads.items(), key=lambda kv: -len(kv[1])))
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"[tracks] {track['name']}：{len(ordered)} 条（新增 {added}），{len(threads)} 个线程")
    return state


def main():
    tracks = load_tracks()
    if not tracks:
        log("[tracks] 没有配置专题"); return
    days = load_days()
    today = now_utc()
    for t in tracks:
        try:
            build_track(t, days, today)
        except Exception as e:  # 单个专题失败不拖垮其他
            log(f"[tracks] {t.get('name')} 失败：{e}")


if __name__ == "__main__":
    main()
