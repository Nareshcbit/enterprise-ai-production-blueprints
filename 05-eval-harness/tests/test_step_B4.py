"""Step B4: rerun every case, take the majority, and compare per case."""

import pytest

from harness.metrics import majority_pass, margin_of_error, paired_diff
from harness.run import evaluate


def test_same_prompt_three_runs_three_scores() -> None:
    report = evaluate("v2", runs=3)
    rates = [round(report.run_pass_rate(r), 2) for r in report.run_ids()]
    assert rates == [0.74, 0.79, 0.71]


def test_margin_of_error_on_100_cases_is_about_9_points() -> None:
    assert margin_of_error(0.74, 100) == pytest.approx(0.086, abs=0.001)


def test_majority_of_three() -> None:
    assert majority_pass({"a": [True, True, False], "b": [True, False, False]}) == {"a": True, "b": False}


def test_v2_majority_pass_rate_is_74_and_c1042_fails_every_run() -> None:
    by_case = evaluate("v2", runs=3).passes_by_case()
    majority = majority_pass(by_case)
    assert sum(majority.values()) == 74
    assert by_case["C-1042"] == [False, False, False]


def test_paired_diff_lists_fixed_and_regressed() -> None:
    diff = paired_diff({"a": True, "b": False, "c": True}, {"a": False, "b": True, "c": True})
    assert diff.fixed == ["b"]
    assert diff.regressed == ["a"]
