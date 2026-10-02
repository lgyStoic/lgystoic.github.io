import importlib.util
import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "radar_alert", Path(__file__).resolve().parents[1] / "tools/radar_alert.py")
radar_alert = importlib.util.module_from_spec(spec)
spec.loader.exec_module(radar_alert)


class RadarAlertTests(unittest.TestCase):
    def test_scheduled_check_uses_latest_elapsed_evening_deadline(self):
        cases = {
            "2026-10-01T18:17:00+08:00": "2026-10-01",
            "2026-10-02T01:03:20+08:00": "2026-10-01",
            "2026-10-02T18:16:59+08:00": "2026-10-01",
            "2026-10-02T18:17:00+08:00": "2026-10-02",
            "2026-01-01T01:00:00+08:00": "2025-12-31",
            "2026-10-01T17:03:20+00:00": "2026-10-01",
        }
        for timestamp, expected in cases.items():
            with self.subTest(timestamp=timestamp):
                self.assertEqual(radar_alert.delivery_day(
                    datetime.fromisoformat(timestamp), "schedule", {}), expected)

    def test_workflow_completion_keeps_originating_run_date(self):
        now = datetime.fromisoformat("2026-10-02T01:03:20+08:00")
        payload = {"workflow_run": {"created_at": "2026-10-01T15:30:00Z"}}
        self.assertEqual(radar_alert.delivery_day(now, "workflow_run", payload), "2026-10-01")
        self.assertEqual(radar_alert.delivery_day(now, "workflow_dispatch", {}), "2026-10-02")

    def test_delayed_schedule_does_not_alert_for_unstarted_next_day(self):
        with patch.dict(radar_alert.os.environ, {"GITHUB_EVENT_NAME": "schedule"}), \
             patch.object(radar_alert, "datetime") as clock, \
             patch.object(radar_alert, "delivered", return_value=True) as delivered, \
             patch.object(radar_alert, "runs_today", return_value=[{"conclusion": "success"}]) as runs, \
             patch.object(radar_alert, "send_alert") as send:
            clock.now.return_value = datetime.fromisoformat("2026-10-02T01:03:20+08:00")
            radar_alert.main()
            delivered.assert_called_once_with(radar_alert.ROOT, "2026-10-01")
            runs.assert_called_once_with("2026-10-01")
            send.assert_not_called()

    def test_delayed_schedule_still_alerts_when_previous_delivery_is_missing(self):
        with patch.dict(radar_alert.os.environ, {"GITHUB_EVENT_NAME": "schedule"}), \
             patch.object(radar_alert, "datetime") as clock, \
             patch.object(radar_alert, "delivered", return_value=False), \
             patch.object(radar_alert, "runs_today", return_value=[]), \
             patch.object(radar_alert, "send_alert", return_value="<alert@example.com>") as send, \
             patch.object(radar_alert, "confirm_delivery") as confirm:
            clock.now.return_value = datetime.fromisoformat("2026-10-02T01:03:20+08:00")
            radar_alert.main()
            send.assert_called_once_with("2026-10-01", [], False)
            confirm.assert_called_once_with("<alert@example.com>")

    def test_delivery_requires_dated_data_and_committed_run_metadata(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "radar/data"
            data.mkdir(parents=True)
            (data / "2026-09-28.json").write_text(json.dumps({"date": "2026-09-28"}))
            (data / "last-run.json").write_text(json.dumps({
                "started_at": "2026-09-28T01:40:31+00:00"}))
            self.assertTrue(radar_alert.delivered(root, "2026-09-28"))
            (data / "last-run.json").write_text(json.dumps({
                "started_at": "2026-09-29T01:40:31+00:00"}))
            self.assertTrue(radar_alert.delivered(root, "2026-09-28"))
            (data / "last-run.json").write_text(json.dumps({
                "started_at": "2026-09-27T01:40:31+00:00"}))
            self.assertFalse(radar_alert.delivered(root, "2026-09-28"))
            (data / "last-run.json").unlink()
            self.assertFalse(radar_alert.delivered(root, "2026-09-28"))

    def test_second_failed_run_or_late_check_alerts(self):
        self.assertFalse(radar_alert.should_alert("workflow_run", 1))
        self.assertTrue(radar_alert.should_alert("workflow_run", 2))
        self.assertFalse(radar_alert.should_alert("workflow_run", 3))
        self.assertTrue(radar_alert.should_alert("schedule", 0))
        self.assertTrue(radar_alert.should_alert("schedule", 2))

    def test_email_contains_run_evidence_without_network_call(self):
        settings = {
            "GITHUB_REPOSITORY": "example/site",
            "RADAR_ALERT_SMTP_HOST": "smtp.example.test",
            "RADAR_ALERT_SMTP_USER": "sender@example.test",
            "RADAR_ALERT_SMTP_PASSWORD": "test-only",
            "RADAR_ALERT_EMAIL_TO": "owner@example.test",
        }
        with patch.dict(radar_alert.os.environ, settings), patch.object(
                radar_alert.smtplib, "SMTP_SSL") as smtp:
            radar_alert.send_alert("2026-09-28", [{
                "id": 123, "conclusion": "cancelled", "url": "https://example.test/run/123"}])
            message = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
            self.assertIn("2026-09-28", message["Subject"])
            self.assertIn("https://example.test/run/123", message.get_content())
            self.assertTrue(message["Message-ID"])

    def test_imap_verifies_exact_message_in_inbox(self):
        settings = {
            "RADAR_ALERT_SMTP_USER": "owner@gmail.com",
            "RADAR_ALERT_SMTP_PASSWORD": "test-only",
            "RADAR_ALERT_EMAIL_TO": "owner@gmail.com",
        }
        with patch.dict(radar_alert.os.environ, settings), \
             patch.object(radar_alert.imaplib, "IMAP4_SSL") as imap:
            mailbox = imap.return_value.__enter__.return_value
            mailbox.select.return_value = ("OK", [b""])
            mailbox.uid.return_value = ("OK", [b"12345"])
            self.assertTrue(radar_alert.verify_inbox_delivery("<alert@example.com>", attempts=1))
            mailbox.uid.assert_called_once_with(
                "search", None, "HEADER", "Message-ID", "<alert@example.com>")

    def test_imap_requires_authenticated_user_to_be_a_recipient(self):
        settings = {
            "RADAR_ALERT_SMTP_USER": "sender@gmail.com",
            "RADAR_ALERT_SMTP_PASSWORD": "test-only",
            "RADAR_ALERT_EMAIL_TO": "owner@example.com",
        }
        with patch.dict(radar_alert.os.environ, settings):
            with self.assertRaisesRegex(RuntimeError, "必须包含 SMTP 登录邮箱"):
                radar_alert.verify_inbox_delivery("<alert@example.com>", attempts=1)

    def test_full_workflow_success_suppresses_alert_but_partial_failure_does_not(self):
        failed = [{"id": i, "conclusion": "cancelled", "url": f"https://example.test/{i}"}
                  for i in (2, 1)]
        with patch.object(radar_alert, "delivered", return_value=True), \
             patch.object(radar_alert, "runs_today", return_value=[{"id": 3, "conclusion": "success"}, *failed]), \
             patch.object(radar_alert, "send_alert") as send:
            radar_alert.main()
            send.assert_not_called()
        with patch.dict(radar_alert.os.environ, {
                "GITHUB_EVENT_NAME": "workflow_run", "GITHUB_EVENT_PATH": "event.json"}), \
             patch.object(radar_alert.Path, "read_text", return_value=json.dumps({
                 "workflow_run": {"created_at": "2026-10-01T15:30:00Z"}})), \
             patch.object(radar_alert, "delivered", return_value=True), \
             patch.object(radar_alert, "runs_today", return_value=failed), \
             patch.object(radar_alert, "send_alert", return_value="<alert@example.com>") as send, \
             patch.object(radar_alert, "confirm_delivery") as confirm:
            radar_alert.main()
            self.assertTrue(send.call_args.args[2])
            confirm.assert_called_once_with("<alert@example.com>")

    def test_manual_email_test_bypasses_delivery_check(self):
        with patch.dict(radar_alert.os.environ, {"RADAR_ALERT_TEST_EMAIL": "1"}), \
             patch.object(radar_alert, "send_test_email") as send, \
             patch.object(radar_alert, "confirm_delivery") as confirm, \
             patch.object(radar_alert, "runs_today") as runs:
            send.return_value = "<test@example.com>"
            radar_alert.main()
            send.assert_called_once()
            confirm.assert_called_once_with("<test@example.com>")
            runs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
