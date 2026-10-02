#!/usr/bin/env python3
"""Email when today's radar delivery is still missing after failed runs."""

from __future__ import annotations

import json
import imaplib
import os
import smtplib
import time
import urllib.request
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Shanghai")


def delivery_day(now: datetime, event: str, payload: dict) -> str:
    """Select a delivery deadline that has elapsed, rather than a new calendar day."""
    local = now.astimezone(TZ)
    if event == "schedule":
        # 与 radar-alert.yml 的 10:17 UTC 同步；跨午夜延迟仍检查上一交付日。
        deadline = local.replace(hour=18, minute=17, second=0, microsecond=0)
        if local < deadline:
            deadline -= timedelta(days=1)
        return deadline.date().isoformat()
    if event == "workflow_run":
        created = payload["workflow_run"]["created_at"]
        return datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(TZ).date().isoformat()
    return local.date().isoformat()


def delivered(root: Path, day: str) -> bool:
    data_path = root / "radar" / "data" / f"{day}.json"
    run_path = root / "radar" / "data" / "last-run.json"
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
        run = json.loads(run_path.read_text(encoding="utf-8"))
        started = datetime.fromisoformat(run["started_at"]).astimezone(TZ)
        # 延迟检查历史日期时，last-run 可能已被下一天成功采集覆盖。
        return data.get("date") == day and started.date().isoformat() >= day
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


def _send_message(msg: EmailMessage) -> str:
    msg["Message-ID"] = make_msgid(domain=os.environ["RADAR_ALERT_SMTP_USER"].split("@")[-1])
    host = os.environ["RADAR_ALERT_SMTP_HOST"]
    port = int(os.environ.get("RADAR_ALERT_SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
        smtp.login(os.environ["RADAR_ALERT_SMTP_USER"], os.environ["RADAR_ALERT_SMTP_PASSWORD"])
        smtp.send_message(msg)
    return msg["Message-ID"]


def verify_inbox_delivery(message_id: str, attempts: int = 6, delay_seconds: int = 5) -> bool:
    """Confirm that Gmail placed this exact message in the authenticated INBOX."""
    user = os.environ["RADAR_ALERT_SMTP_USER"]
    recipients = {item.strip().lower() for item in os.environ["RADAR_ALERT_EMAIL_TO"].split(",")}
    if user.lower() not in recipients:
        raise RuntimeError("无法自检收件：RADAR_ALERT_EMAIL_TO 必须包含 SMTP 登录邮箱")
    host = os.environ.get("RADAR_ALERT_IMAP_HOST", "imap.gmail.com")
    for attempt in range(attempts):
        with imaplib.IMAP4_SSL(host, 993, timeout=20) as mailbox:
            mailbox.login(user, os.environ["RADAR_ALERT_SMTP_PASSWORD"])
            status, _ = mailbox.select("INBOX", readonly=True)
            if status != "OK":
                raise RuntimeError("Gmail IMAP 无法读取 INBOX")
            status, matches = mailbox.uid("search", None, "HEADER", "Message-ID", message_id)
            if status == "OK" and matches and matches[0].strip():
                return True
        if attempt + 1 < attempts:
            time.sleep(delay_seconds)
    return False


def send_alert(day: str, failures: list[dict], core_delivered: bool = False) -> str:
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
    return _send_message(msg)


def send_test_email(day: str) -> str:
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
    return _send_message(msg)


def confirm_delivery(message_id: str) -> None:
    if not verify_inbox_delivery(message_id):
        raise RuntimeError("邮件已通过 SMTP 提交，但在等待窗口内未出现在 Gmail 收件箱")


def should_alert(event: str, failed_count: int) -> bool:
    # 第二次失败立即告警；晚间兜底始终复查未落库，避免监控任务自身漏跑。
    return (event == "workflow_run" and failed_count == 2) or event != "workflow_run"


def main() -> None:
    now = datetime.now(TZ)
    day = now.date().isoformat()
    if os.environ.get("RADAR_ALERT_TEST_EMAIL") == "1":
        message_id = send_test_email(day)
        confirm_delivery(message_id)
        print(f"{day} Gmail SMTP 测试邮件已提交，并由 IMAP 确认进入收件箱")
        return
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    payload = {}
    if event == "workflow_run":
        payload = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    day = delivery_day(now, event, payload)
    print(f"检查交付日期 {day}；触发方式 {event or 'manual'}；执行时间 {now.isoformat()}")
    core_delivered = delivered(ROOT, day)
    runs = runs_today(day)
    failures = [run for run in runs if run["conclusion"] in {"failure", "cancelled", "timed_out"}]
    if core_delivered and runs and runs[0]["conclusion"] == "success":
        print(f"{day} 雷达及后续阶段已完成，无需告警")
        return
    if not should_alert(event, len(failures)):
        print(f"{day} 尚未落库；{len(failures)} 次失败/取消，本次不重复发信")
        return
    message_id = send_alert(day, failures, core_delivered)
    confirm_delivery(message_id)
    print(f"{day} 流程未完整交付；邮件已由 IMAP 确认进入收件箱，失败/取消运行 {len(failures)} 次")


if __name__ == "__main__":
    main()
