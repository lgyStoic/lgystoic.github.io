#!/usr/bin/env python3
"""流水线自检：不需要模型，跑在 radar.yml 最后一步。

做三件事：
  1. 统计每个源的连续失败 / 连续 0 条天数（radar/data/health.json），连续失败 ≥ 3 天的源自动停用
     （在 sources 配置里写 "disabled": true 和原因，radar.py / events.py 会跳过）。
  2. 记录 AI 是否退回规则、定时是否触发（连续天数），供状态页和人判断。
  3. 写当天的巡检报告 radar/checks/<日期>.md（≤ 8 行），/status/ 页渲染。

需要模型判断的事（解析格式变了、活动抽取明显错、要不要加源）只写进「待人决定」，
由 Claude 会话（定时或按需）或 Garry 本人处理。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "radar" / "data"
HEALTH = DATA / "health.json"
LAST_RUN = DATA / "last-run.json"
CHECKS = ROOT / "radar" / "checks"
SOURCES = ROOT / "radar" / "sources.json"
EVENT_SOURCES = ROOT / "radar" / "event_sources.json"
TZ = ZoneInfo("Asia/Shanghai")
DISABLE_AFTER = 3  # 连续失败天数


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    health = load(HEALTH, {"sources": {}, "ai_fallback_streak": 0, "schedule_miss_streak": 0, "last_checked": ""})
    if health.get("last_checked") == today:
        # 同一天多次运行：不重复累加连续天数，只重写报告
        same_day = True
    else:
        same_day = False

    day = load(DATA / f"{today}.json", {})
    events = load(DATA / "events.json", {})
    run = load(LAST_RUN, {})
    reason = os.environ.get("RADAR_TRIGGER_REASON", "")

    # ---- 源健康 ----
    problems, fixed = [], []
    configs = {"radar": (SOURCES, load(SOURCES, {})), "events": (EVENT_SOURCES, load(EVENT_SOURCES, {}))}
    statuses = {"radar": day.get("sources", []), "events": events.get("sources", [])}
    for kind, rows in statuses.items():
        cfg_path, cfg = configs[kind]
        by_id = {s["id"]: s for s in cfg.get("sources", [])}
        changed = False
        for s in rows:
            key = f"{kind}:{s['id']}"
            h = health["sources"].setdefault(key, {"fail": 0, "zero": 0, "name": s["name"]})
            h["name"] = s["name"]
            if not same_day:
                if not s.get("ok"):
                    h["fail"] += 1
                    h["zero"] = 0
                elif s.get("total", s.get("count", 0)) == 0:
                    h["zero"] += 1  # 抓通了但一条都解析不出来：多半是前端渲染或格式变了
                    h["fail"] = 0
                else:
                    h["fail"] = h["zero"] = 0
                    h["last_ok"] = today
            src = by_id.get(s["id"])
            if h["fail"] >= DISABLE_AFTER and src is not None and not src.get("disabled"):
                src["disabled"] = True
                src["disabled_reason"] = f"{today} 自动停用：连续 {h['fail']} 天失败（{(s.get('error') or '')[:60]}）"
                changed = True
                fixed.append(f"自动停用 {s['name']}（连续 {h['fail']} 天失败）")
            elif not s.get("ok"):
                problems.append(f"{s['name']} 失败 ×{h['fail']}：{(s.get('error') or '')[:50]}")
            elif h["zero"] >= 3:
                problems.append(f"{s['name']} 连续 {h['zero']} 天解析出 0 条（前端渲染或格式变了）")
        if changed:
            dump(cfg_path, cfg)

    # ---- AI / 定时 ----
    ai_ok = bool(day.get("ai"))
    if not same_day:
        health["ai_fallback_streak"] = 0 if ai_ok else health.get("ai_fallback_streak", 0) + 1
        if reason == "schedule_missed":
            health["schedule_miss_streak"] = health.get("schedule_miss_streak", 0) + 1
        elif run.get("event") == "schedule":
            health["schedule_miss_streak"] = 0
    if not ai_ok:
        problems.append(f"AI 退回规则（连续 {health['ai_fallback_streak']} 天）")

    # ---- 待人决定 ----
    decide = []
    if health["ai_fallback_streak"] >= 2:
        decide.append("AI 连续两天退回规则，检查 GEMINI_API_KEY / 配额")
    if health["schedule_miss_streak"] >= 2:
        decide.append("定时连续两天没触发，考虑改 cron 时间或换触发方式")
    for kind, rows in statuses.items():
        for s in rows:
            err = s.get("error") or ""
            if "not well-formed" in err or "mismatched tag" in err or "JSON" in err:
                decide.append(f"{s['name']} 的格式解析失败，需要人看一眼源是否改版")
    undated = [e for e in events.get("events", []) if not e.get("start") and not e.get("deadline") and e.get("relevance") != "low"]
    if len(undated) >= 10:
        decide.append(f"{len(undated)} 个非低相关活动没有日期，抽取可能需要调")

    # ---- 报告 ----
    c = day.get("counts", {})
    ev_new = sum(1 for e in events.get("events", []) if e.get("found") == today)
    ev_undated = len(undated)
    run_kind = {"schedule": "定时 ✓", "workflow_dispatch": "手动", "push": "触发文件"}.get(run.get("event", ""), run.get("event", "?"))
    if reason == "schedule_missed":
        run_kind = "定时 ✗（08:40 补跑）"
    model = day.get("model") or "规则"
    lines = [
        f"📅 {today} 巡检（自动）",
        f"运行：{run_kind} ｜ AI：{model} ｜ 简报 {len(day.get('items', []))} 条（必看 {c.get('high', 0)}）｜ 活动新增 {ev_new}（无日期 {ev_undated}）",
        "问题：" + ("；".join(problems[:6]) if problems else "无"),
        "已修：" + ("；".join(fixed) if fixed else "无"),
        "待人决定：" + ("；".join(decide) if decide else "无"),
    ]
    CHECKS.mkdir(parents=True, exist_ok=True)
    (CHECKS / f"{today}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    health["last_checked"] = today
    health["needs_agent"] = decide
    dump(HEALTH, health)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
