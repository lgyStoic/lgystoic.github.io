"""直接执行工作流中的阶段规划，覆盖定时、补跑与诊断分支。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / '.github/workflows/xhs.yml').read_text()
PLAN = textwrap.dedent(WORKFLOW.split('<<\'PYTHON\' >> "$GITHUB_OUTPUT"\n', 1)[1].split('          PYTHON', 1)[0])


class WorkflowTests(unittest.TestCase):
    def plan(self, **overrides):
        env = dict(os.environ, MODE='', SCHEDULE='', CHECK_MODEL='', CHECK_SVG='', INPUT_DATE='2026-09-27')
        env.update(overrides)
        result = subprocess.run([sys.executable, '-c', PLAN], cwd=ROOT, env=env,
                                text=True, capture_output=True, check=True)
        output = dict(line.split('=', 1) for line in result.stdout.splitlines())
        self.assertEqual(output['date'], '2026-09-27')
        return json.loads(output['stages'])

    def test_daily_stages_have_separate_track_jobs(self):
        self.assertEqual(self.plan(SCHEDULE='37 1 * * *'), ['cards', 'track:video', 'track:world'])

    def test_weekly_schedule_only_runs_jobs(self):
        self.assertEqual(self.plan(SCHEDULE='53 1 * * 1'), ['jobs'])

    def test_manual_tracks_and_diagnostics_do_not_regenerate_cards(self):
        self.assertEqual(self.plan(MODE='tracks'), ['track:video', 'track:world'])
        self.assertEqual(self.plan(CHECK_MODEL='true', CHECK_SVG='true'), ['check-model', 'check-svg'])
        self.assertEqual(self.plan(MODE='all'), ['cards', 'jobs', 'track:video', 'track:world'])


if __name__ == '__main__':
    unittest.main()
