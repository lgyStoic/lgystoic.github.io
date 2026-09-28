import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import xhs
from xhs_state import RunState
REAL_GH_PUT = xhs.gh_put


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.remote = {}
        self.patches = [
            patch.object(xhs, 'DATA', self.data),
            patch.object(xhs, 'gh_get_text', side_effect=lambda repo, path, token: self.remote.get(path, '')),
            patch.object(xhs, 'gh_put', side_effect=lambda repo, path, data, token, msg: self.remote.__setitem__(path, data.decode())),
            patch.dict(xhs.os.environ, {'INBOX_TOKEN': 'test', 'INBOX_REPO': 'test/private', 'XHS_IMAGES': '0'}),
        ]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def test_delivered_draft_is_not_overwritten_or_reordered(self):
        self.remote['posts/cards/2026-09-27.md'] = '原稿与既有顺序'
        callback = Mock()
        self.assertEqual(xhs.run_stage('cards', '2026-09-27', callback), 'existing')
        callback.assert_not_called()
        self.assertEqual(self.remote['posts/cards/2026-09-27.md'], '原稿与既有顺序')

    def test_api_write_rejects_replacing_an_existing_draft(self):
        previous = {'sha': 'test', 'content': base64.b64encode(b'original').decode()}
        response = lambda: io.BytesIO(json.dumps(previous).encode())
        with patch.object(xhs.urllib.request, 'urlopen', return_value=response()) as request:
            with self.assertRaises(ValueError):
                REAL_GH_PUT('test/private', 'posts/cards/2026-09-27.md', b'changed', 'test', 'test')
            self.assertEqual(request.call_count, 1)
        with patch.object(xhs.urllib.request, 'urlopen', return_value=response()) as request:
            REAL_GH_PUT('test/private', 'posts/cards/2026-09-27.md', b'original', 'test', 'test')
            self.assertEqual(request.call_count, 1)

    def test_changed_delivered_draft_does_not_repair_old_topic_mapping(self):
        def interrupted():
            xhs.CURRENT_RUN.put('delivery', {'sha256': 'different'})
            xhs.CURRENT_RUN.put('topics_update', {'topics': {}, 'posts': [{'id': 'A'}]})
            self.remote['posts/cards/2026-09-27.md'] = '人工修订后的版本'
            raise RuntimeError('interrupted')
        with self.assertRaises(RuntimeError):
            xhs.run_stage('cards', '2026-09-27', interrupted)
        with self.assertRaises(ValueError):
            xhs.run_stage('cards', '2026-09-27', Mock())
        self.assertNotIn('posts/topics.json', self.remote)

    def test_topic_order_is_frozen_and_stable_ids_are_supported(self):
        posts = [{'id': 'A', 'entity': '主体A', 'title': '稿件A'}, {'id': 'B', 'entity': '主体B', 'title': '稿件B'}]
        xhs.save_topics('test/private', 'test', {}, '2026-09-27', posts)
        self.remote['posts/stats.md'] = 'cards/2026-09-27#01\ncards/2026-09-27@B'
        with self.assertRaises(ValueError):
            xhs.save_topics('test/private', 'test', {}, '2026-09-27', posts[::-1])
        history, topics = xhs.load_topic_history('test/private', 'test', '2026-09-28')
        self.assertEqual([r['title'] for r in history if r['posted']], ['稿件A', '稿件B'])
        self.assertEqual(topics['2026-09-27'][0]['material_id'], 'cards/2026-09-27@A')

    def test_remote_checkpoint_survives_runner_loss(self):
        read = lambda path: self.remote.get(path, '')
        write = lambda path, data: self.remote.__setitem__(path, data.decode())
        schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']}
        model = Mock(return_value={'ok': True})
        state = RunState('cards', '2026-09-27', self.data / 'first', read, write)
        self.assertEqual(state.pin('source', lambda: {'version': 1}), {'version': 1})
        state.model_call(model, 'system', 'request', schema)
        fresh = RunState('cards', '2026-09-27', self.data / 'new-runner', read, write)
        self.assertEqual(fresh.pin('source', lambda: {'version': 2}), {'version': 1})
        self.assertEqual(fresh.model_call(model, 'system', 'request', schema), {'ok': True})
        self.assertEqual(model.call_count, 1)

    def test_invalid_response_and_failed_remote_save_can_retry(self):
        state = RunState('cards', '2026-09-27', self.data)
        schema = {'type': 'object', 'required': ['ok'], 'properties': {'ok': {'type': 'boolean'}}}
        call = Mock(side_effect=[{}, {'ok': True}])
        self.assertEqual(state.model_call(call, 's', 'u', schema), {})
        self.assertEqual(state.model_call(call, 's', 'u', schema), {'ok': True})
        state.write_remote = Mock(side_effect=RuntimeError('写入失败'))
        with self.assertRaises(RuntimeError): state.finish('completed')

    def test_resume_after_markdown_write_repairs_topics_without_new_draft(self):
        def interrupted():
            xhs.CURRENT_RUN.put('topics_update', {'topics': {}, 'posts': [{'id': 'A', 'entity': 'A'}]})
            self.remote['posts/cards/2026-09-27.md'] = '已交付'
            raise RuntimeError('模拟写稿后中断')
        with self.assertRaises(RuntimeError):
            xhs.run_stage('cards', '2026-09-27', interrupted)
        callback = Mock()
        xhs.run_stage('cards', '2026-09-27', callback)
        callback.assert_not_called()
        self.assertEqual(json.loads(self.remote['posts/topics.json'])['2026-09-27'][0]['id'], 'A')

    def test_card_resume_only_generates_missing_posts_and_pins_source(self):
        date = '2026-09-27'
        rows = [{'id': str(i), 'title': f'来源{i}', 'summary': '来源摘要', 'priority': 'high'} for i in range(6)]
        (self.data / f'{date}.json').write_text(json.dumps({'items': rows}))
        failing = True
        calls = []

        def model(system, message, schema, *, label):
            self.assertTrue(label.startswith('xhs-'))
            candidates, _ = json.JSONDecoder().raw_decode(message.split('JSON，请逐条生成，每条只输出一个对象：\n', 1)[1])
            ids = [r['id'] for r in candidates]
            calls.append(ids)
            if failing and any(int(i) >= 3 for i in ids): return None
            return {'posts': [dict(id=i, title='标题'+i, headline='标题'+i, body='正文', takeaways=['要点'], tags=['标签'],
                                  image_prompt='', entity='主体'+i, novelty='new', followup_of='') for i in ids]}

        with patch.object(xhs, '_call_llm_json', side_effect=model), \
             patch.object(xhs, 'shorten_titles'), \
             patch.object(xhs, 'rank_posts', side_effect=lambda posts, byid: posts), \
             patch.object(xhs, 'episode_number', return_value=1):
            with self.assertRaises(SystemExit):
                xhs.run_stage('cards', date, lambda: xhs.run_cards(date))
            self.assertNotIn(f'posts/cards/{date}.md', self.remote)
            # 上游已变化，恢复仍消费第一次锁定的六条。
            (self.data / f'{date}.json').write_text('{"items": []}')
            failing = False
            xhs.run_stage('cards', date, lambda: xhs.run_cards(date))
        self.assertEqual(calls.count(['0', '1', '2']), 1)
        self.assertIn('cards/2026-09-27@5', self.remote[f'posts/cards/{date}.md'])
        self.assertEqual(len(json.loads(self.remote['posts/topics.json'])[date]), 6)

    def test_track_failure_returns_nonzero_after_other_tracks_continue(self):
        tracks = [{'id': 'a', 'post': True, 'name': 'A'}, {'id': 'b', 'post': True, 'name': 'B'}]
        with patch.object(sys, 'argv', ['xhs.py', '--tracks']), patch.object(xhs, 'load_tracks', return_value=tracks), \
             patch.object(xhs, 'run_stage', side_effect=[SystemExit('failed'), 'skipped']) as stage:
            with self.assertRaises(SystemExit): xhs.main()
            self.assertEqual(stage.call_count, 2)


if __name__ == '__main__':
    unittest.main()
