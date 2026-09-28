import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import publish_results as pipeline


def git(path, *args):
    return subprocess.run(['git', *args], cwd=path, check=True, capture_output=True).stdout


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


class PublishResultsTests(unittest.TestCase):
    def test_rejected_radar_push_preserves_new_jobs_and_source_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote, radar, jobs = (root / name for name in ('remote.git', 'radar', 'jobs'))
            git(root, 'init', '--bare', '--initial-branch=master', str(remote))
            git(root, 'clone', str(remote), str(radar))
            for key, value in [('user.name', 'test'), ('user.email', 'test@example.com')]:
                git(radar, 'config', key, value)
            write(radar / 'radar/data/jobs.json', '{"version":"old"}')
            write(radar / 'radar/data/contributions.json', '{"version":"old"}')
            config = {'sources': [{'id': 'a', 'weight': 1}, {'id': 'b', 'weight': 1}]}
            write(radar / 'radar/sources.json', json.dumps(config))
            write(radar / 'tools/build.py', 'from pathlib import Path\nPath("index.html").write_text(Path("radar/data/jobs.json").read_text())\n')
            git(radar, 'add', '-A'); git(radar, 'commit', '-m', 'initial'); git(radar, 'push', 'origin', 'master')
            git(root, 'clone', str(remote), str(jobs))
            for key, value in [('user.name', 'test'), ('user.email', 'test@example.com')]:
                git(jobs, 'config', key, value)
            # radar 开始后另一工作流先推送，包含配置人工编辑。
            write(jobs / 'radar/data/jobs.json', '{"version":"new-jobs"}')
            write(jobs / 'radar/data/contributions.json', '{"version":"new-contributions"}')
            updated = {'sources': [{'id': 'a', 'weight': 9}, {'id': 'b', 'disabled': True, 'disabled_reason': '人工确认'}]}
            write(jobs / 'radar/sources.json', json.dumps(updated))
            git(jobs, 'add', '-A'); git(jobs, 'commit', '-m', 'new inputs'); git(jobs, 'push', 'origin', 'master')
            write(radar / 'radar/data/2026-09-28.json', '{"items":[1]}')
            for source in config['sources']:
                source.update(disabled=True, disabled_reason='自动停用')
            write(radar / 'radar/sources.json', json.dumps(config))
            pipeline.publish(radar, 'radar', '雷达测试')
            git(jobs, 'pull', '--ff-only')
            self.assertIn('new-jobs', (jobs / 'radar/data/jobs.json').read_text())
            self.assertIn('new-contributions', (jobs / 'radar/data/contributions.json').read_text())
            self.assertIn('new-jobs', (jobs / 'index.html').read_text())
            self.assertTrue((jobs / 'radar/data/2026-09-28.json').exists())
            got = json.loads((jobs / 'radar/sources.json').read_text())['sources']
            self.assertEqual(got[0], {'id': 'a', 'weight': 9, 'disabled': True, 'disabled_reason': '自动停用'})
            self.assertEqual(got[1]['disabled_reason'], '人工确认')

    def test_ownership_excludes_other_jobs_and_private_checkpoints(self):
        self.assertTrue(pipeline.owns('radar', 'radar/data/tracks/video.json'))
        for name in ('jobs.json', 'contributions.json', 'xhs-state/cards/2026-09-28.json'):
            self.assertFalse(pipeline.owns('radar', 'radar/data/' + name))
        self.assertFalse(pipeline.owns('jobs', 'radar/data/events.json'))
        self.assertFalse(pipeline.owns('contributions', 'radar/data/jobs.json'))


if __name__ == '__main__':
    unittest.main()
