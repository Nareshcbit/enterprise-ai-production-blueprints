"""LLM-as-judge for the free-text reason, and its calibration against adjusters."""

from __future__ import annotations

from harness.models import Verdict

TRUST_THRESHOLD = 0.85


def parse_verdict(output: str) -> Verdict:
    """Step C2: parse the judge's JSON. Raises ValidationError if it is not a Verdict."""
    raise NotImplementedError("Step C2: implement parse_verdict")


def agreement(judge_outputs: dict[str, str], adjuster_grades: dict[str, str]) -> float:
    """Step C2: share of calibration items where the judge's verdict equals the adjuster's.

    An unparseable or missing judge output counts as a disagreement.
    """
    raise NotImplementedError("Step C2: implement agreement")


def judge_is_trusted(score: float) -> bool:
    return score >= TRUST_THRESHOLD
