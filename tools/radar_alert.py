#!/usr/bin/env python3
"""Email when today's radar delivery is still missing after failed runs."""

from __future__ import annotations

import json
import os
import smtplib
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Shanghai")


def delivered(root: Path, day: str) -> bool:
    data_path = root / "radar" / "data" / f"{day}.json"
    run_path = root / "radar" / "data" / "last-run.json"
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
        run = json.loads(run_path.read_text(encoding="utf-8"))
        started = datetime.fromisoformat(run["started_at"]).astimezone(TZ)
        return data.get("date") == day and started.date().isoformat() == day
    except (OSError, ValueError, KeyError, TypeError):
        return False


def failed_runs_today(day: str) -> list[dict]:
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    url = f"https://api.github.com/repos/{repo}/actions/workflows/radar.yml/runs?per_page=30"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "radar-delivery-alert",
    })
    with urllib.request.urlopen(req, timeout=20) as response:
        runs = json.load(response).get("workflow_runs", [])
    return [
        {"id": run["id"], "conclusion": run["conclusion"], "url": run["html_url"]}
        for run in runs
        if run.get("conclusion") in {"failure", "cancelled", "timed_out"}
        and datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")).astimezone(TZ).date().isoformat() == day
    ]


def send_alert(day: str, failures: list[dict]) -> None:
    names = ("RADAR_ALERT_SMTP_HOST", "RADAR_ALERT_SMTP_USER",
             "RADAR_ALERT_SMTP_PASSWORD", "RADAR_ALERT_EMAIL_TO")
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise RuntimeError("邮件告警未配置 GitHub Actions secrets: " + ", ".join(missing))
    repo = os.environ["GITHUB_REPOSITORY"]
    msg = EmailMessage()
    msg["Subject"] = f"[雷达告警] {day} 内容仍未落库"
    msg["From"] = os.environ.get("RADAR_ALERT_EMAIL_FROM") or os.environ["RADAR_ALERT_SMTP_USER"]
    msg["To"] = os.environ["RADAR_ALERT_EMAIL_TO"]
    lines = [f"北京时间 {day} 的雷达数据与完整运行记录尚未同时落库。",
             f"检查位置：https://github.com/{repo}/actions/workflows/radar.yml", "",
             "当日失败或取消的运行："]
    lines += [f"- {run['id']} {run['conclusion']} {run['url']}" for run in failures]
    if not failures:
        lines.append("- 未查到当日失败或取消记录；请检查调度是否触发及产物提交。")
    lines += ["", "此邮件不触发采集补跑；请先核对 Actions 日志和远端产物。"]
    msg.set_content("\n".join(lines))
    host = os.environ["RADAR_ALERT_SMTP_HOST"]
    port = int(os.environ.get("RADAR_ALERT_SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
        smtp.login(os.environ["RADAR_ALERT_SMTP_USER"], os.environ["RADAR_ALERT_SMTP_PASSWORD"])
        smtp.send_message(msg)


def should_alert(event: str, failed_count: int) -> bool:
    # 第二次失败立即告警；晚间兜底始终复查未落库，避免监控任务自身漏跑。
    return (event == "workflow_run" and failed_count == 2) or event != "workflow_run"


def main() -> None:
    day = datetime.now(TZ).date().isoformat()
    if delivered(ROOT, day):
        print(f"{day} 雷达已落库，无需告警")
        return
    failures = failed_runs_today(day)
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    if not should_alert(event, len(failures)):
        print(f"{day} 尚未落库；{len(failures)} 次失败/取消，本次不重复发信")
        return
    send_alert(day, failures)
    print(f"{day} 未落库；已发送邮件告警，失败/取消运行 {len(failures)} 次")


if __name__ == "__main__":
    main()
