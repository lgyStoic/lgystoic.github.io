#!/usr/bin/env python3
"""Build a versioned manifest from generated files without copying their bodies."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root, paths):
    out = []
    for relative, kind in paths:
        path = root / relative
        if not path.is_file():
            continue
        out.append({
            "artifact_id": str(relative), "version": digest(path),
            "sha256": digest(path), "kind": kind,
            "source_uri": f"repo:{relative}",
        })
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": out}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    paths = [(Path("radar/data/last-run.json"), "silver"),
             (Path("radar/data/events.json"), "silver"),
             (Path("radar/data/tracks/video.json"), "silver"),
             (Path("radar/data/tracks/world.json"), "silver")]
    result = build(Path(args.root), paths)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifacts": len(result["artifacts"]), "output": args.output}))


if __name__ == "__main__":
    main()
