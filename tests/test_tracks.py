import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('tracks', TOOLS / 'tracks.py')
tracks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tracks)


class TracksTests(unittest.TestCase):
    def test_digest_records_actual_model(self):
        original = tracks.call_llm_json

        def fake_call(*_args, **_kwargs):
            tracks.radar.LAST_MODEL_USED = 'gemini-test-version'
            return {'digest': '本周有实质进展。', 'highlights': ['新版本'], 'sota': []}

        tracks.call_llm_json = fake_call
        try:
            state = {}
            entries = [{'date': '2026-09-20', 'entity': 'Example', 'kind': 'release',
                        'title': 'Example 1.0', 'summary': 'released', 'link': 'https://example.com'}]
            tracks.write_digest({'id': 'test', 'name': '测试'}, state, entries,
                                datetime(2026, 9, 20, tzinfo=timezone.utc))
            self.assertEqual(state['digest']['model'], 'gemini-test-version')
        finally:
            tracks.call_llm_json = original


if __name__ == '__main__':
    unittest.main()
