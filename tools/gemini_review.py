#!/usr/bin/env python3
"""Run an evidence-first LLM review for a supplied Git diff."""

import argparse
import json
from pathlib import Path

import radar


SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "verdict": {"type": "string", "enum": ["approve", "request_changes"]},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["blocking", "important", "minor"],
                    },
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "title": {"type": "string"},
                    "evidence": {"type": "string"},
                    "impact": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                },
                "required": [
                    "severity",
                    "file",
                    "line",
                    "title",
                    "evidence",
                    "impact",
                    "suggested_fix",
                ],
            },
        },
        "tests_to_add": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "verdict", "findings", "tests_to_add"],
}

SYSTEM = """You are a senior SGLang diffusion-runtime maintainer reviewing a patch.
Review only issues supported by the supplied diff and context. Prioritize correctness
of dynamic batching: request compatibility, prompt/image/seed/output alignment,
batch dimensions, CFG, multi-output behavior, and regressions for other pipelines.
Every finding must name an exact changed file and a line from the patch. Do not invent
framework APIs or report style-only nits. Mark blocking only when the change can cause
incorrect output, a deterministic runtime failure, data loss, or a broad regression.
If there are no supported findings, return an empty findings list and approve."""


def render(review: dict, model: str) -> str:
    lines = [
        "# LLM code review",
        "",
        f"Model: `{model}`",
        "",
        f"Verdict: **{review['verdict']}**",
        "",
        review["summary"],
        "",
        "## Findings",
        "",
    ]
    if not review["findings"]:
        lines.append("No evidence-backed findings.")
    for finding in review["findings"]:
        lines.extend(
            [
                f"### {finding['severity']}: {finding['title']}",
                "",
                f"`{finding['file']}:{finding['line']}`",
                "",
                finding["evidence"],
                "",
                f"Impact: {finding['impact']}",
                "",
                f"Suggested fix: {finding['suggested_fix']}",
                "",
            ]
        )
    lines.extend(["## Tests to add", ""])
    lines.extend(f"- {item}" for item in review["tests_to_add"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diff", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    diff = args.diff.read_text(encoding="utf-8")
    if not diff.strip():
        raise SystemExit("Diff is empty; refusing to ask the model for a review.")
    review = radar.call_llm_json(SYSTEM, f"Review this patch:\n\n{diff}", SCHEMA, label="code-review")
    if review is None:
        raise SystemExit("The model did not return a structured code review.")
    args.out.write_text(render(review, radar.LAST_MODEL_USED or "unknown"), encoding="utf-8")


if __name__ == "__main__":
    main()
