import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "radar_alert", Path(__file__).resolve().parents[1] / "tools/radar_alert.py")
radar_alert = importlib.util.module_from_spec(spec)
spec.loader.exec_module(radar_alert)


class RadarAlertTests(unittest.TestCase):
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

    def test_full_workflow_success_suppresses_alert_but_partial_failure_does_not(self):
        failed = [{"id": i, "conclusion": "cancelled", "url": f"https://example.test/{i}"}
                  for i in (2, 1)]
        with patch.object(radar_alert, "delivered", return_value=True), \
             patch.object(radar_alert, "runs_today", return_value=[{"id": 3, "conclusion": "success"}, *failed]), \
             patch.object(radar_alert, "send_alert") as send:
            radar_alert.main()
            send.assert_not_called()
        with patch.dict(radar_alert.os.environ, {"GITHUB_EVENT_NAME": "workflow_run"}), \
             patch.object(radar_alert, "delivered", return_value=True), \
             patch.object(radar_alert, "runs_today", return_value=failed), \
             patch.object(radar_alert, "send_alert") as send:
            radar_alert.main()
            self.assertTrue(send.call_args.args[2])

    def test_manual_email_test_bypasses_delivery_check(self):
        with patch.dict(radar_alert.os.environ, {"RADAR_ALERT_TEST_EMAIL": "1"}), \
             patch.object(radar_alert, "send_test_email") as send, \
             patch.object(radar_alert, "runs_today") as runs:
            radar_alert.main()
            send.assert_called_once()
            runs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
