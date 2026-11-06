"""Graders: decide whether one output passes one case."""

from __future__ import annotations

from pydantic import ValidationError

from harness.models import Triage


def grade_string(output: str, expected: str) -> bool:
    """The naive grader from step A2: exact string match on free text."""
    return output == expected


def parse_triage(output: str) -> Triage:
    """Step A3: parse the assistant's JSON into a Triage. Raises ValidationError if it is not one."""
    return Triage.model_validate_json(output)


def grade_enum(output: str, expected: str) -> bool:
    """Step A3: pass only if the output parses AND its priority equals the label."""
    try:
        triage = parse_triage(output)
    except ValidationError:
        return False
    return triage.priority == expected
