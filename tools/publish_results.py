#!/usr/bin/env python3
"""Actions 提交结果：冲突后只恢复当前管线的数据，使用最新代码重建页面。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(['git', *args], cwd=root, check=check, capture_output=True)


def changed_paths(root: Path) -> list[str]:
    changed = git(root, 'diff', '--name-only', '-z', 'HEAD').stdout
    new = git(root, 'ls-files', '--others', '--exclude-standard', '-z').stdout
    return sorted(set(p.decode() for p in (changed + new).split(b'\0') if p))


def owns(owner: str, path: str) -> bool:
    if owner == 'jobs':
        return path == 'radar/data/jobs.json'
    if owner == 'contributions':
        return path == 'radar/data/contributions.json'
    return bool(re.fullmatch(
        r'radar/(?:data/(?:\d{4}-\d{2}-\d{2}\.json|events\.json|seen\.json|'
        r'health\.json|last-run\.(?:json|log)|tracks/[^/]+\.json)|checks/[^/]+\.md)', path))


def snapshot(root: Path, owner: str) -> tuple[dict, dict]:
    files, patches = {}, {}
    for name in changed_paths(root):
        path = root / name
        if owns(owner, name):
            files[name] = path.read_bytes() if path.exists() else None
        if owner == 'radar' and name in ('radar/sources.json', 'radar/event_sources.json'):
            before = json.loads(git(root, 'show', f'HEAD:{name}').stdout)
            after = json.loads(path.read_bytes())
            old = {s['id']: s for s in before['sources']}
            changes = []
            for source in after['sources']:
                previous = old.get(source['id'])
                if previous is None:
                    continue
                fields = ('disabled', 'disabled_reason')
                a = {k: previous[k] for k in fields if k in previous}
                b = {k: source[k] for k in fields if k in source}
                if a != b:
                    changes.append((source['id'], a, b))
            if changes:
                patches[name] = changes
    return files, patches


def restore(root: Path, files: dict, patches: dict) -> None:
    for name, content in files.items():
        path = root / name
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    for name, changes in patches.items():
        path = root / name
        data = json.loads(path.read_bytes())
        sources = {s['id']: s for s in data['sources']}
        changed = False
        for source_id, before, after in changes:
            source = sources.get(source_id)
            if source is None:
                continue
            current = {k: source[k] for k in ('disabled', 'disabled_reason') if k in source}
            if current != before:
                print(f'保留远端源状态：{name} / {source_id}', flush=True)
                continue
            for key in ('disabled', 'disabled_reason'):
                source.pop(key, None)
            source.update(after)
            changed = True
        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def publish(root: Path, owner: str, message: str, attempts: int = 3) -> None:
    files, patches = snapshot(root, owner)
    for attempt in range(attempts):
        git(root, 'add', '-A')
        if git(root, 'diff', '--cached', '--quiet', check=False).returncode == 0:
            print('没有变化，跳过提交')
            return
        git(root, 'commit', '-q', '-m', message)
        pushed = git(root, 'push', 'origin', 'HEAD:master', check=False)
        if pushed.returncode == 0:
            return
        # 鉴权、规则等其他错误也会在有限次数后明确失败。
        print(f'推送失败，第 {attempt + 1}/{attempts} 次：{pushed.stderr.decode()}', flush=True)
        if attempt + 1 == attempts:
            raise RuntimeError('结果未推送成功')
        git(root, 'fetch', 'origin', 'master')
        git(root, 'reset', '--hard', 'origin/master')
        restore(root, files, patches)
        subprocess.run([sys.executable, 'tools/build.py'], cwd=root, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('owner', choices=['radar', 'jobs', 'contributions'])
    ap.add_argument('--message', required=True)
    args = ap.parse_args()
    publish(Path(__file__).resolve().parents[1], args.owner, args.message)


if __name__ == '__main__':
    main()
