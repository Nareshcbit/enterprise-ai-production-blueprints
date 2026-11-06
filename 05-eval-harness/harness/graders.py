"""Graders: decide whether one output passes one case."""

from __future__ import annotations

from harness.models import Triage


def grade_string(output: str, expected: str) -> bool:
    """The naive grader from step A2: exact string match on free text."""
    return output == expected


def parse_triage(output: str) -> Triage:
    """Step A3: parse the assistant's JSON into a Triage. Raises ValidationError if it is not one.

    Hint: pydantic models can validate a JSON string directly.
    """
    raise NotImplementedError("Step A3: implement parse_triage")


def grade_enum(output: str, expected: str) -> bool:
    """Step A3: pass only if the output parses AND its priority equals the label.

    An output that does not parse is a failed case, not a crash.
    """
    raise NotImplementedError("Step A3: implement grade_enum")
