#!/usr/bin/env python3
"""Build a private, channel-oriented delivery bundle from the inbox checkout."""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def copy_files(root, target, patterns):
    found = []
    for pattern in patterns:
        for source in sorted(root.glob(pattern)):
            if not source.is_file():
                continue
            relative = source.relative_to(root)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            found.append({"path": str(relative), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    return found


def build(root, output):
    root, output = Path(root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    xhs = copy_files(root, output / "xiaohongshu", ["posts/cards/**/*.md", "posts/cards/**/*.jpg",
                                                       "posts/jobs/**/*.md", "posts/jobs/**/*.jpg",
                                                       "posts/tracks/**/*.md", "posts/tracks/**/*.jpg"])
    manifest = {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "channels": {
            "xiaohongshu": {"status": "ready" if xhs else "empty", "files": xhs},
            "wechat_official": {"status": "optional_not_ready", "files": []},
            "wechat_channels": {"status": "optional_not_ready", "files": []},
        },
        "review": {"status": "needs_review", "platform_submission": "manual"},
    }
    (output / "delivery.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = build(args.root, args.output)
    print(json.dumps({"xiaohongshu_files": len(manifest["channels"]["xiaohongshu"]["files"]), "output": args.output}))


if __name__ == "__main__":
    main()
