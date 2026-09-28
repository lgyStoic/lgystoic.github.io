"""文稿恢复状态。私有远端是权威副本；本地缓存必须 gitignore。"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path


def valid_response(value, schema):
    """只缓存符合当前提示词结构的响应，格式错误仍允许下次重试。"""
    expected = schema.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'boolean': bool,
             'number': (int, float), 'integer': int}
    if expected in types and not isinstance(value, types[expected]):
        return False
    if 'enum' in schema and value not in schema['enum']:
        return False
    if isinstance(value, dict):
        if any(k not in value for k in schema.get('required', [])):
            return False
        return all(valid_response(v, schema.get('properties', {}).get(k, {})) for k, v in value.items())
    if isinstance(value, list):
        return all(valid_response(v, schema.get('items', {})) for v in value)
    return True


class RunState:
    def __init__(self, kind: str, date: str, local: Path, read=None, write=None):
        self.path = f'posts/.pipeline/{kind}/{date}.json'
        self.local = local / kind / f'{date}.json'
        self.write_remote = write
        raw = read(self.path) if read else (self.local.read_text() if self.local.exists() else '')
        self.data = json.loads(raw) if raw else {}
        if self.data and (self.data.get('kind'), self.data.get('date')) != (kind, date):
            raise ValueError('恢复状态与本次批次不一致')
        if not self.data or self.data.get('status') == 'skipped':
            self.data = {'version': 1, 'kind': kind, 'date': date, 'status': 'running',
                         'values': {}, 'responses': {}}

    def save(self):
        raw = json.dumps(self.data, ensure_ascii=False, indent=2) + '\n'
        # 远端保存失败必须停止；不能报告一个下一次无法恢复的成功批次。
        if self.write_remote:
            self.write_remote(self.path, raw.encode())
        self.local.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.local.with_suffix('.tmp')
        tmp.write_text(raw)
        tmp.replace(self.local)

    def pin(self, key, factory):
        if key not in self.data['values']:
            self.data['values'][key] = factory()
            self.save()
        return deepcopy(self.data['values'][key])

    def put(self, key, value):
        self.data['values'][key] = deepcopy(value)
        self.save()

    def model_call(self, call, system, user_msg, schema, *, label='llm'):
        key = hashlib.sha256(json.dumps([system, user_msg, schema, label],
                            ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if key not in self.data['responses']:
            result = call(system, user_msg, schema, label=label)
            if not result or not valid_response(result, schema):
                return result
            if 'posts' in result and (not result['posts'] or any(
                not all(isinstance(p.get(k), str) and p[k].strip() for k in ('title', 'body', 'headline'))
                for p in result['posts'])):
                return result
            self.data['responses'][key] = result
            self.save()
        return deepcopy(self.data['responses'][key])

    def finish(self, status):
        self.data['status'] = status
        self.save()
