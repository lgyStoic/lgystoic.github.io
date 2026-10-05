#!/usr/bin/env python3
"""Minimal, restart-safe handoff registry for the content pipeline.

The registry stores metadata only. Source documents stay in their owning
repositories; versions are pinned by commit/blob and SHA-256.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "service" / "content-flow.sqlite3"
SCHEMA = Path(__file__).with_name("schema.sql")

STATUSES = {"draft", "sent", "accepted", "in_progress", "needs_input",
            "ready_for_review", "completed", "blocked", "cancelled"}
TRANSITIONS = {
    "draft": {"sent", "cancelled"}, "sent": {"accepted", "blocked", "cancelled"},
    "accepted": {"in_progress", "needs_input", "blocked", "cancelled"},
    "in_progress": {"needs_input", "ready_for_review", "completed", "blocked", "cancelled"},
    "needs_input": {"in_progress", "blocked", "cancelled"},
    "ready_for_review": {"completed", "needs_input", "blocked"},
    "blocked": {"in_progress", "cancelled"}, "completed": set(), "cancelled": set(),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def connect(path=DEFAULT_DB):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA.read_text(encoding="utf-8"))
    return db


def register_handoff(db, *, handoff_id, input_keys, sender_role, recipient_role,
                     requested_action, idempotency_key=None, status="draft", metadata=None):
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status}")
    idem = idempotency_key or handoff_id
    existing = db.execute("SELECT id FROM handoffs WHERE idempotency_key=?", (idem,)).fetchone()
    if existing:
        return existing["id"], False
    stamp = now()
    db.execute("""INSERT INTO handoffs
        (id, input_keys, sender_role, recipient_role, requested_action, status,
         idempotency_key, metadata, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (handoff_id, json.dumps(input_keys, ensure_ascii=False), sender_role,
         recipient_role, requested_action, status, idem,
         json.dumps(metadata or {}, ensure_ascii=False), stamp, stamp))
    db.execute("INSERT INTO audit_log (handoff_id, event, detail, created_at) VALUES (?, ?, ?, ?)",
               (handoff_id, "created", status, stamp))
    db.commit()
    return handoff_id, True


def transition(db, handoff_id, new_status, *, detail="", evidence=None):
    if new_status not in STATUSES:
        raise ValueError(f"unknown status: {new_status}")
    row = db.execute("SELECT status FROM handoffs WHERE id=?", (handoff_id,)).fetchone()
    if not row:
        raise KeyError(handoff_id)
    old = row["status"]
    if new_status != old and new_status not in TRANSITIONS[old]:
        raise ValueError(f"invalid transition {old} -> {new_status}")
    stamp = now()
    db.execute("""UPDATE handoffs SET status=?, evidence=?, updated_at=? WHERE id=?""",
               (new_status, json.dumps(evidence or {}, ensure_ascii=False), stamp, handoff_id))
    db.execute("INSERT INTO audit_log (handoff_id, event, detail, created_at) VALUES (?, ?, ?, ?)",
               (handoff_id, "status", json.dumps({"from": old, "to": new_status, "detail": detail}, ensure_ascii=False), stamp))
    db.commit()


def import_legacy(db, path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    imported = 0
    for item in data.get("items", []):
        status = item.get("work_status") or "draft"
        if status == "in_progress" and item.get("receipt", {}).get("decision") == "accepted":
            status = "in_progress"
        hid, created = register_handoff(
            db, handoff_id=item["id"], input_keys=item.get("input_keys", []),
            sender_role="silver_data", recipient_role="research_editorial",
            requested_action=item.get("next_action", "处理交接任务"),
            idempotency_key=item["id"], status=status,
            metadata={"legacy": True, "legacy_receipt": item.get("receipt"),
                      "legacy_run_evidence": item.get("run_evidence")})
        if created:
            imported += 1
            if item.get("receipt"):
                db.execute("UPDATE handoffs SET evidence=? WHERE id=?",
                           (json.dumps(item["receipt"], ensure_ascii=False), hid))
    db.commit()
    return imported


def list_queue(db):
    return [dict(row) for row in db.execute(
        "SELECT id, recipient_role, status, requested_action, updated_at FROM handoffs "
        "WHERE status NOT IN ('completed','cancelled') ORDER BY updated_at").fetchall()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import-legacy"); imp.add_argument("path")
    sub.add_parser("queue")
    args = parser.parse_args()
    db = connect(args.db)
    if args.command == "import-legacy":
        print(json.dumps({"imported": import_legacy(db, args.path)}, ensure_ascii=False))
    else:
        print(json.dumps(list_queue(db), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
