"""Load cases, recorded outputs and the judge calibration set from disk."""

from __future__ import annotations

import json
from pathlib import Path

from harness.models import Case

LAB_ROOT = Path(__file__).resolve().parent.parent


def read_jsonl(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def load_cases() -> list[Case]:
    return [Case.model_validate(row) for row in read_jsonl(LAB_ROOT / "data/cases.jsonl")]


def load_recording(prompt: str) -> dict[tuple[str, int], str]:
    """Recorded raw outputs for a prompt version, keyed by (case id, run)."""
    rows = read_jsonl(LAB_ROOT / f"recordings/triage_{prompt}.jsonl")
    return {(row["id"], row["run"]): row["output"] for row in rows}


def load_calibration() -> list[dict]:
    return read_jsonl(LAB_ROOT / "data/judge_calibration.jsonl")


def load_judge_recording() -> dict[str, str]:
    return {row["id"]: row["output"] for row in read_jsonl(LAB_ROOT / "recordings/judge.jsonl")}


def load_prompt(name: str) -> str:
    return (LAB_ROOT / f"prompts/{name}.md").read_text()
