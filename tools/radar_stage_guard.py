#!/usr/bin/env python3
"""Decide which radar stages already have a committed Beijing-date result."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from radar_alert import delivered

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Shanghai")


def load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def updated_today(value: str, day: str) -> bool:
    try:
        return datetime.fromisoformat(value).astimezone(TZ).date().isoformat() == day
    except (TypeError, ValueError):
        return False


def stage_skips(root: Path, day: str, event: str) -> dict[str, bool]:
    if event != "schedule":
        return {name: False for name in ("radar", "events", "tracks")}
    events = load(root / "radar/data/events.json")
    config = load(root / "radar/tracks.json")
    track_ids = [item["id"] for item in config.get("tracks", []) if isinstance(item, dict) and item.get("id")]
    tracks_done = "tracks" in config and all(updated_today(
        load(root / f"radar/data/tracks/{track_id}.json").get("updated"), day)
        for track_id in track_ids)
    return {
        "radar": delivered(root, day),
        "events": events.get("today") == day,
        "tracks": tracks_done,
    }


def main() -> None:
    day = datetime.now(TZ).date().isoformat()
    skips = stage_skips(ROOT, day, "schedule")
    if os.environ.get("RADAR_GUARD_MODE") == "health":
        print(f"missing={'false' if all(skips.values()) else 'true'}")
        return
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        skips = {name: False for name in skips}
    for name, skip in skips.items():
        print(f"skip_{name}={'true' if skip else 'false'}")
        print(f"{name}: {'已交付，跳过' if skip else '需要运行'}", file=__import__("sys").stderr)


if __name__ == "__main__":
    main()
