"""LLM-as-judge for the free-text reason, and its calibration against adjusters."""

from __future__ import annotations

from pydantic import ValidationError

from harness.models import Verdict

TRUST_THRESHOLD = 0.85


def parse_verdict(output: str) -> Verdict:
    """Step C2: parse the judge's JSON. Raises ValidationError if it is not a Verdict."""
    return Verdict.model_validate_json(output)


def agreement(judge_outputs: dict[str, str], adjuster_grades: dict[str, str]) -> float:
    """Step C2: share of calibration items where the judge's verdict equals the adjuster's.
    An unparseable judge output counts as a disagreement."""
    agreed = 0
    for item_id, grade in adjuster_grades.items():
        try:
            agreed += parse_verdict(judge_outputs[item_id]).verdict == grade
        except (KeyError, ValidationError):
            continue
    return agreed / len(adjuster_grades)


def judge_is_trusted(score: float) -> bool:
    return score >= TRUST_THRESHOLD
