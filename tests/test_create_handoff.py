import json
from tools.content_flow.create_handoff import create


def test_handoff_is_deterministic_and_deduplicates(tmp_path):
    manifest = {"artifacts": [{"artifact_id": "a", "version": "v1", "sha256": "x", "kind": "silver", "source_uri": "u"}]}
    one = tmp_path / "one.json"
    two = tmp_path / "two.json"
    one.write_text(json.dumps(manifest))
    two.write_text(json.dumps(manifest))
    first = create([one, two])
    second = create([two, one])
    assert first["handoff_id"] == second["handoff_id"]
    assert len(first["input_artifacts"]) == 1
    assert first["status"] == "sent"
