#!/usr/bin/env python3
"""Send and verify a Gmail alert for an overdue handoff."""
import os
import smtplib
import imaplib
from email.message import EmailMessage
from email.utils import make_msgid


def send(result):
    user = os.environ["RADAR_ALERT_SMTP_USER"]
    msg = EmailMessage()
    msg["Subject"] = f"[内容交接告警] {result['handoff_id']} {result['status']}"
    msg["From"] = os.environ.get("RADAR_ALERT_EMAIL_FROM") or user
    msg["To"] = os.environ["RADAR_ALERT_EMAIL_TO"]
    msg.set_content(f"交接 {result['handoff_id']} 当前状态：{result['status']}。\n请打开 Actions 产物核对输入版本和接收回执。")
    msg["Message-ID"] = make_msgid(domain=user.split("@")[-1])
    with smtplib.SMTP_SSL(os.environ.get("RADAR_ALERT_SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("RADAR_ALERT_SMTP_PORT", "465")), timeout=20) as smtp:
        smtp.login(user, os.environ["RADAR_ALERT_SMTP_PASSWORD"])
        smtp.send_message(msg)
    with imaplib.IMAP4_SSL(os.environ.get("RADAR_ALERT_IMAP_HOST", "imap.gmail.com"), 993, timeout=20) as mailbox:
        mailbox.login(user, os.environ["RADAR_ALERT_SMTP_PASSWORD"])
        mailbox.select("INBOX", readonly=True)
        status, matches = mailbox.uid("search", None, "HEADER", "Message-ID", msg["Message-ID"])
        if status != "OK" or not matches or not matches[0].strip():
            raise RuntimeError("告警已提交但未在 Gmail 收件箱确认")
