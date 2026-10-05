"""Immutable artifact registration; bodies remain in the owning store."""
import hashlib
import re
from pathlib import Path

from .content_flow import now


def register(db, *, artifact_id, version, sha256, kind, source_uri):
    if not artifact_id or not version or not source_uri:
        raise ValueError('artifact identity, version and source are required')
    if not re.fullmatch(r'[0-9a-f]{64}', sha256):
        raise ValueError('invalid SHA-256')
    if kind not in {'silver', 'research', 'creative', 'delivery'}:
        raise ValueError('invalid artifact kind')
    with db:
        db.execute('INSERT OR IGNORE INTO artifacts VALUES (?,?,?,?,?,?)',
                   (artifact_id, version, sha256, kind, source_uri, now()))
        row = db.execute('SELECT * FROM artifacts WHERE artifact_id=? AND version=?',
                         (artifact_id, version)).fetchone()
        if (row['sha256'], row['kind'], row['source_uri']) != (sha256, kind, source_uri):
            raise ValueError('immutable artifact version conflict')
    return dict(row)


def register_file(db, path, **identity):
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return register(db, sha256=digest, **identity)
