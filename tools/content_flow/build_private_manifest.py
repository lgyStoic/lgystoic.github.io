#!/usr/bin/env python3
"""Hash private inbox outputs without copying their contents into public artifacts."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    root = Path(args.root)
    patterns = ["posts/cards/*.md", "posts/jobs/*.md", "posts/tracks/**/*.md"]
    artifacts = []
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            relative = path.relative_to(root).as_posix()
            kind = "silver" if "/cards/" in f"/{relative}" else "research"
            artifacts.append({"artifact_id": f"radar-inbox:{relative}", "version": digest,
                              "sha256": digest, "kind": kind,
                              "source_uri": f"private-repo:{relative}"})
    result = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
              "artifacts": artifacts}
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifacts": len(artifacts), "output": args.output}))


if __name__ == "__main__":
    main()
