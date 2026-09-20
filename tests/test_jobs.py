import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('jobs', Path(__file__).resolve().parents[1] / 'tools/jobs.py')
jobs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jobs)
PROFILE = json.loads(jobs.CONFIG.read_text())['profile']

class JobsTests(unittest.TestCase):
    def job(self, **extra):
        return dict({'title': 'Inference Engineer', 'location': 'Shenzhen', 'url': 'https://example.org/job/1', 'description': 'CUDA inference optimization', 'source': 'test', 'company': 'Example'}, **extra)

    def test_location_and_evidence(self):
        result = jobs.match(self.job(), PROFILE)
        self.assertIn('训推加速', result['tags'])
        self.assertEqual(result['region'], '深圳')
        self.assertGreater(result['score'], jobs.match(self.job(location='Remote, US only'), PROFILE)['score'])

    def test_no_company_boilerplate_matches(self):
        self.assertIsNone(jobs.match(self.job(title='Account Executive'), PROFILE))
        self.assertIsNone(jobs.match(self.job(title='Frontend Engineer', description='Web applications'), PROFILE))
        self.assertIsNone(jobs.match(self.job(title='Research Scientist', description='credit editorial'), PROFILE))

    def test_unrelated_roles_with_technical_words(self):
        for title in ["Technical Recruiter, AI Research", "Research Economist", "Data Scientist, Marketing", "Security Engineer, GPU"]:
            self.assertIsNone(jobs.match(self.job(title=title), PROFILE))

    def test_failed_source_retains_but_successful_removes(self):
        config = {'sources': [{'id': 'test', 'name': 'Example'}], 'profile': PROFILE}
        old = {'jobs': [dict(jobs.match(self.job(), PROFILE), last_seen='2026-09-01')]}
        def fail(source):
            raise TimeoutError()
        stale = jobs.collect(config, old, fail)
        self.assertTrue(stale['jobs'][0]['stale'])
        self.assertEqual(stale['jobs'][0]['last_seen'], '2026-09-01')
        self.assertEqual(jobs.collect(config, old, lambda _: [])['jobs'], [])

    def test_duplicates_and_unsafe_urls(self):
        config = {'sources': [{'id':'test', 'name':'Example'}], 'profile': PROFILE}
        result = jobs.collect(config, {}, lambda _: [self.job(), self.job(), self.job(url='javascript:alert(1)')])
        self.assertEqual(len(result['jobs']), 1)

    def test_headhunters_are_deduplicated_and_capped(self):
        rows = []
        for i in range(12):
            row = jobs.match(self.job(title=f'Inference Engineer {i % 4}', url=f'https://example.org/job/{i}', company=f'某公司{i}'), PROFILE)
            rows.append(dict(row, listing_type='headhunter', last_seen='2026-09-20', stale=False))
        profile = dict(PROFILE, max_headhunter_total=3, max_headhunter_per_region=2)
        result = jobs.limit_jobs(rows, profile)
        self.assertEqual(len(result), 2)

    def test_visible_region_caps_keep_remainder(self):
        rows = [dict(jobs.match(self.job(title=f'Inference Engineer {i}', url=f'https://example.org/job/{i}'), PROFILE), last_seen='2026-09-20') for i in range(5)]
        visible, extra = jobs.split_visible_jobs(rows, {'visible_region_caps': {'深圳': 2}})
        self.assertEqual((len(visible), len(extra)), (2, 3))

if __name__ == '__main__':
    unittest.main()
