"""Step C2: an LLM judge for free text, trusted only after calibration against adjusters."""

import pytest
from pydantic import ValidationError

from harness.data import load_calibration, load_judge_recording
from harness.judge import agreement, judge_is_trusted, parse_verdict


def test_parses_verdict() -> None:
    v = parse_verdict('{"verdict": "fail", "rule_violated": "uninhabitable_home"}')
    assert v.verdict == "fail"
    assert v.rule_violated == "uninhabitable_home"


def test_rejects_free_text_verdict() -> None:
    with pytest.raises(ValidationError):
        parse_verdict("Looks fine to me")


def test_unparseable_judge_output_counts_as_disagreement() -> None:
    assert agreement({"x": "nope"}, {"x": "pass"}) == 0.0


def test_judge_agrees_with_adjusters_88_percent_and_is_trusted() -> None:
    grades = {it["id"]: it["adjuster_grade"] for it in load_calibration()}
    score = agreement(load_judge_recording(), grades)
    assert score == pytest.approx(0.88)
    assert judge_is_trusted(score)


def test_judge_fails_the_c1042_reason() -> None:
    v = parse_verdict(load_judge_recording()["C-1042"])
    assert (v.verdict, v.rule_violated) == ("fail", "uninhabitable_home")
