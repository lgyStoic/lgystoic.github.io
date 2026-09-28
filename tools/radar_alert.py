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


def runs_today(day: str) -> list[dict]:
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
        {"id": run["id"], "conclusion": run.get("conclusion"), "url": run["html_url"]}
        for run in runs
        if datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")).astimezone(TZ).date().isoformat() == day
    ]


def send_alert(day: str, failures: list[dict], core_delivered: bool = False) -> None:
    names = ("RADAR_ALERT_SMTP_HOST", "RADAR_ALERT_SMTP_USER",
             "RADAR_ALERT_SMTP_PASSWORD", "RADAR_ALERT_EMAIL_TO")
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise RuntimeError("邮件告警未配置 GitHub Actions secrets: " + ", ".join(missing))
    repo = os.environ["GITHUB_REPOSITORY"]
    msg = EmailMessage()
    msg["Subject"] = f"[雷达告警] {day} 流程未完整交付"
    msg["From"] = os.environ.get("RADAR_ALERT_EMAIL_FROM") or os.environ["RADAR_ALERT_SMTP_USER"]
    msg["To"] = os.environ["RADAR_ALERT_EMAIL_TO"]
    state = "雷达主数据已落库，但后续阶段未全部成功" if core_delivered else "雷达主数据尚未落库"
    lines = [f"北京时间 {day}：{state}。",
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


def send_test_email(day: str) -> None:
    names = ("RADAR_ALERT_SMTP_HOST", "RADAR_ALERT_SMTP_USER",
             "RADAR_ALERT_SMTP_PASSWORD", "RADAR_ALERT_EMAIL_TO")
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise RuntimeError("邮件告警未配置 GitHub Actions secrets: " + ", ".join(missing))
    msg = EmailMessage()
    msg["Subject"] = f"[雷达告警测试] {day} Gmail SMTP 配置成功"
    msg["From"] = os.environ.get("RADAR_ALERT_EMAIL_FROM") or os.environ["RADAR_ALERT_SMTP_USER"]
    msg["To"] = os.environ["RADAR_ALERT_EMAIL_TO"]
    msg.set_content(
        "这是一封手动触发的配置测试邮件。\n\n"
        "GitHub Actions 已通过 Gmail SMTP 完成认证并提交邮件。\n"
        "此测试没有触发采集、补跑或生产告警。\n"
    )
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
    if os.environ.get("RADAR_ALERT_TEST_EMAIL") == "1":
        send_test_email(day)
        print(f"{day} Gmail SMTP 测试邮件已提交")
        return
    core_delivered = delivered(ROOT, day)
    runs = runs_today(day)
    failures = [run for run in runs if run["conclusion"] in {"failure", "cancelled", "timed_out"}]
    if core_delivered and runs and runs[0]["conclusion"] == "success":
        print(f"{day} 雷达及后续阶段已完成，无需告警")
        return
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    if not should_alert(event, len(failures)):
        print(f"{day} 尚未落库；{len(failures)} 次失败/取消，本次不重复发信")
        return
    send_alert(day, failures, core_delivered)
    print(f"{day} 流程未完整交付；已发送邮件告警，失败/取消运行 {len(failures)} 次")


if __name__ == "__main__":
    main()
