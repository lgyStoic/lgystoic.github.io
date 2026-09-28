import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import radar_stage_guard


class RadarStageGuardTests(unittest.TestCase):
    def test_only_committed_current_stage_outputs_are_skipped(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "radar/data"
            (data / "tracks").mkdir(parents=True)
            (root / "radar/tracks.json").write_text(json.dumps({
                "tracks": [{"id": "video"}, {"id": "world"}]}))
            (data / "2026-09-28.json").write_text(json.dumps({"date": "2026-09-28"}))
            (data / "last-run.json").write_text(json.dumps({
                "started_at": "2026-09-28T01:30:00+00:00"}))
            (data / "events.json").write_text(json.dumps({"today": "2026-09-27"}))
            (data / "tracks/video.json").write_text(json.dumps({
                "updated": "2026-09-28T01:35:00+00:00"}))
            (data / "tracks/world.json").write_text(json.dumps({
                "updated": "2026-09-27T01:35:00+00:00"}))
            self.assertEqual(radar_stage_guard.stage_skips(root, "2026-09-28", "schedule"), {
                "radar": True, "events": False, "tracks": False})
            self.assertEqual(radar_stage_guard.stage_skips(root, "2026-09-28", "workflow_dispatch"), {
                "radar": False, "events": False, "tracks": False})


if __name__ == "__main__":
    unittest.main()
