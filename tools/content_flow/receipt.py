#!/usr/bin/env python3
"""Validate a downstream receipt against a handoff and its deadline."""
import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

DECISIONS = {"accepted", "in_progress", "needs_input", "ready_for_review", "completed", "blocked", "cancelled"}


def check(handoff, receipt=None, *, timeout_hours=24, at=None):
    at = at or datetime.now(timezone.utc)
    created = datetime.fromisoformat(handoff["created_at"])
    expired = at > created + timedelta(hours=timeout_hours)
    if receipt is None:
        return {"ok": not expired, "status": "overdue" if expired else "awaiting_receipt",
                "handoff_id": handoff["handoff_id"]}
    if receipt.get("handoff_id") != handoff["handoff_id"]:
        return {"ok": False, "status": "receipt_mismatch", "handoff_id": handoff["handoff_id"]}
    decision = receipt.get("decision")
    if decision not in DECISIONS:
        return {"ok": False, "status": "invalid_decision", "handoff_id": handoff["handoff_id"]}
    if decision == "completed" and not receipt.get("evidence"):
        return {"ok": False, "status": "missing_completion_evidence", "handoff_id": handoff["handoff_id"]}
    if decision in {"needs_input", "blocked"} and not receipt.get("next_action"):
        return {"ok": False, "status": "missing_next_action", "handoff_id": handoff["handoff_id"]}
    return {"ok": decision not in {"blocked", "needs_input"}, "status": decision,
            "handoff_id": handoff["handoff_id"], "next_action": receipt.get("next_action", "")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("handoff")
    parser.add_argument("--receipt")
    parser.add_argument("--timeout-hours", type=int, default=24)
    args = parser.parse_args()
    handoff = json.loads(Path(args.handoff).read_text(encoding="utf-8"))
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8")) if args.receipt and Path(args.receipt).exists() else None
    result = check(handoff, receipt, timeout_hours=args.timeout_hours)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
