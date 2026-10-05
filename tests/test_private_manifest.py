import json
from tools.content_flow.build_private_manifest import main


def test_private_manifest_contains_hashes_only(tmp_path, monkeypatch):
    root = tmp_path / "inbox"
    (root / "posts/cards").mkdir(parents=True)
    (root / "posts/cards/2026-10-05.md").write_text("private report")
    out = tmp_path / "manifest.json"
    monkeypatch.setattr("sys.argv", ["build_private_manifest", "--root", str(root), "--output", str(out)])
    main()
    data = json.loads(out.read_text())
    assert len(data["artifacts"]) == 1
    assert "private report" not in out.read_text()
    assert len(data["artifacts"][0]["sha256"]) == 64
