import json
from tools.content_flow.package_delivery import build


def test_delivery_bundle_is_channelized_and_hashed(tmp_path):
    root = tmp_path / "inbox"
    (root / "posts/cards/2026-10-05").mkdir(parents=True)
    (root / "posts/cards/2026-10-05/report.md").write_text("daily report")
    output = tmp_path / "delivery"
    result = build(root, output)
    assert result["channels"]["xiaohongshu"]["status"] == "ready"
    assert result["channels"]["wechat_official"]["status"] == "optional_not_ready"
    data = json.loads((output / "delivery.json").read_text())
    assert data["channels"]["xiaohongshu"]["files"][0]["sha256"]
    assert (output / "xiaohongshu/posts/cards/2026-10-05/report.md").exists()
    assert "daily report" not in (output / "delivery.json").read_text()
