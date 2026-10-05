import pytest
from tools.content_flow.content_flow import connect
from tools.content_flow.artifacts import register_file


def test_artifact_survives_restart_and_rejects_changed_content(tmp_path):
    source = tmp_path / 'source.md'
    source.write_text('original')
    database = tmp_path / 'registry.sqlite3'
    identity = dict(artifact_id='cards/day', version='commit-a', kind='silver',
                    source_uri='private:posts/day.md')
    db = connect(database)
    first = register_file(db, source, **identity)
    assert register_file(db, source, **identity) == first
    db.close()
    db = connect(database)
    assert register_file(db, source, **identity) == first
    source.write_text('changed')
    with pytest.raises(ValueError, match='conflict'):
        register_file(db, source, **identity)
    assert db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0] == 1
    assert db.execute('SELECT sha256 FROM artifacts').fetchone()[0] == first['sha256']
    register_file(db, source, **dict(identity, version='commit-b'))
    assert db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0] == 2
