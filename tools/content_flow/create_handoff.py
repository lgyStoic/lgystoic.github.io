#!/usr/bin/env python3
"""Create a deterministic handoff envelope from versioned artifact manifests."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def create(manifest_paths, *, sender="silver_data", recipient="research_editorial"):
    artifacts = []
    for path in manifest_paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        artifacts.extend(data.get("artifacts", []))
    artifacts.sort(key=lambda item: (item.get("artifact_id", ""), item.get("version", "")))
    unique = []
    seen = set()
    for item in artifacts:
        key = (item["artifact_id"], item["version"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    fingerprint = hashlib.sha256(json.dumps(unique, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    stamp = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "handoff_id": f"silver-increment-{fingerprint}",
        "created_at": stamp,
        "sender_role": sender,
        "recipient_role": recipient,
        "status": "sent",
        "idempotency_key": f"silver:{fingerprint}",
        "requested_action": "核对来源版本，完成事实研究并回写接收回执",
        "input_artifacts": unique,
        "next_action": "接收方写回 accepted/in_progress 回执；超时由调度器告警",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifests", nargs="+", help="manifest JSON files")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    handoff = create(args.manifests)
    Path(args.output).write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"handoff_id": handoff["handoff_id"], "artifacts": len(handoff["input_artifacts"])}))


if __name__ == "__main__":
    main()
