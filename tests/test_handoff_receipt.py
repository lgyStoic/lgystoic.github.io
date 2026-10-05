from datetime import datetime, timezone
from tools.content_flow.receipt import check


def test_timeout_and_completion_require_evidence():
    handoff = {"handoff_id": "h1", "created_at": "2026-10-01T00:00:00+00:00"}
    at = datetime(2026, 10, 3, tzinfo=timezone.utc)
    assert check(handoff, at=at)["status"] == "overdue"
    assert check(handoff, {"handoff_id": "h2", "decision": "accepted"}, at=at)["status"] == "receipt_mismatch"
    assert check(handoff, {"handoff_id": "h1", "decision": "completed"}, at=at)["status"] == "missing_completion_evidence"
    assert check(handoff, {"handoff_id": "h1", "decision": "completed", "evidence": "delivery.json"}, at=at)["ok"]


def test_blocked_receipt_requires_next_action():
    handoff = {"handoff_id": "h1", "created_at": "2026-10-01T00:00:00+00:00"}
    receipt = {"handoff_id": "h1", "decision": "blocked"}
    assert check(handoff, receipt)["status"] == "missing_next_action"
    receipt["next_action"] = "补齐一手来源"
    assert check(handoff, receipt)["status"] == "blocked"
    assert not check(handoff, receipt)["ok"]
