import tempfile
import unittest
from pathlib import Path

from content_flow import connect, import_legacy, register_handoff, transition, list_queue


class ServiceTests(unittest.TestCase):
    def test_idempotent_and_valid_state_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = connect(Path(tmp) / "flow.sqlite3")
            self.assertEqual(register_handoff(db, handoff_id="h1", input_keys=["a@1"],
                sender_role="silver_data", recipient_role="research_editorial",
                requested_action="核验"), ("h1", True))
            self.assertEqual(register_handoff(db, handoff_id="h1-copy", input_keys=["a@1"],
                sender_role="silver_data", recipient_role="research_editorial",
                requested_action="重复", idempotency_key="h1"), ("h1", False))
            for status in ("sent", "accepted", "in_progress", "ready_for_review", "completed"):
                transition(db, "h1", status)
            self.assertEqual(list_queue(db), [])

    def test_legacy_import_preserves_id_and_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "handoffs.json"
            source.write_text('{"items":[{"id":"legacy-1","input_keys":["x"],"work_status":"in_progress","receipt":{"decision":"accepted"}}]}')
            db = connect(Path(tmp) / "flow.sqlite3")
            self.assertEqual(import_legacy(db, source), 1)
            self.assertEqual(import_legacy(db, source), 0)
            row = db.execute("SELECT id,status FROM handoffs").fetchone()
            self.assertEqual(tuple(row), ("legacy-1", "in_progress"))


if __name__ == "__main__":
    unittest.main()
