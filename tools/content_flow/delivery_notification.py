#!/usr/bin/env python3
"""Notify the owner that a channel delivery bundle is ready."""
import os
import smtplib
import imaplib
from email.message import EmailMessage
from email.utils import make_msgid


def send(*, run_url, artifact_name, channels):
    user = os.environ["RADAR_ALERT_SMTP_USER"]
    msg = EmailMessage()
    msg["Subject"] = "[内容交付] 今日渠道交付包已生成"
    msg["From"] = os.environ.get("RADAR_ALERT_EMAIL_FROM") or user
    msg["To"] = os.environ["RADAR_ALERT_EMAIL_TO"]
    msg["Message-ID"] = make_msgid(domain=user.split("@")[-1])
    lines = ["今日内容交付包已生成。", "", f"Actions 运行页：{run_url}",
             f"交付包名称：{artifact_name}", "", "渠道状态："]
    lines.extend(f"- {name}: {status}" for name, status in channels.items())
    lines += ["", "请在发布前完成人工审看和平台预检。"]
    msg.set_content("\n".join(lines))
    with smtplib.SMTP_SSL(os.environ.get("RADAR_ALERT_SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("RADAR_ALERT_SMTP_PORT", "465")), timeout=20) as smtp:
        smtp.login(user, os.environ["RADAR_ALERT_SMTP_PASSWORD"])
        smtp.send_message(msg)
    with imaplib.IMAP4_SSL(os.environ.get("RADAR_ALERT_IMAP_HOST", "imap.gmail.com"), 993, timeout=20) as mailbox:
        mailbox.login(user, os.environ["RADAR_ALERT_SMTP_PASSWORD"])
        mailbox.select("INBOX", readonly=True)
        status, matches = mailbox.uid("search", None, "HEADER", "Message-ID", msg["Message-ID"])
        if status != "OK" or not matches or not matches[0].strip():
            raise RuntimeError("交付通知已提交但未在 Gmail 收件箱确认")
