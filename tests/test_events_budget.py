from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import events


class EventsBudgetTests(unittest.TestCase):
    def test_second_batch_uses_defaults_after_time_budget(self):
        candidates = [{
            "id": str(i), "source": "test", "default_type": "other",
            "default_city": "", "title": "example", "description": "",
            "hints": {}, "link": "https://example.test",
        } for i in range(31)]
        with patch.dict(events.os.environ, {"EVENTS_AI_BUDGET_SECONDS": "600"}), \
             patch.object(events.time, "monotonic", side_effect=[0, 0, 601]), \
             patch.object(events, "call_llm_json", return_value={"items": [{"id": "0"}]}) as call:
            self.assertEqual(events.enrich_events(candidates, "2026-09-28"), {"0": {"id": "0"}})
            call.assert_called_once()


if __name__ == "__main__":
    unittest.main()
