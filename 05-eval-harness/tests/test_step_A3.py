"""Step A3: force structured output and grade it in code."""

import pytest
from pydantic import ValidationError

from harness.graders import grade_enum, parse_triage
from harness.run import evaluate


def test_parses_valid_json() -> None:
    triage = parse_triage('{"priority": "urgent", "reason": "Family displaced."}')
    assert triage.priority == "urgent"


@pytest.mark.parametrize(
    "bad", ["Urgent.", '{"priority": "Urgent", "reason": "x"}', '{"priority": "urgent"}']
)
def test_rejects_anything_outside_the_schema(bad: str) -> None:
    with pytest.raises(ValidationError):
        parse_triage(bad)


def test_unparseable_output_fails_the_case_instead_of_crashing() -> None:
    assert grade_enum("Priority: urgent", "urgent") is False


def test_string_grader_on_free_text_says_58_percent() -> None:
    assert evaluate("v1", grader="string").run_pass_rate(0) == pytest.approx(0.58)


def test_enum_grader_on_structured_output_says_74_percent() -> None:
    assert evaluate("v2", grader="enum").run_pass_rate(0) == pytest.approx(0.74)
