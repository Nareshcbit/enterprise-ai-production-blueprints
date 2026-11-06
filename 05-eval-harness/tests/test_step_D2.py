"""Step D2: the CI gate blocks per-case regressions that a rising total hides."""

import pytest

from harness.gate import check_gate
from harness.metrics import majority_pass, paired_diff
from harness.run import evaluate, matrix_for


def gate_for(prompt: str):
    baseline = majority_pass(evaluate("v2", runs=3).passes_by_case())
    report = evaluate(prompt, runs=3)
    candidate = majority_pass(report.passes_by_case())
    rate = sum(candidate.values()) / len(candidate)
    return rate, check_gate(rate, matrix_for(report), baseline, candidate)


def test_v3_total_rises_and_passes_old_bars_but_regresses_4_fast_track_cases() -> None:
    rate, result = gate_for("v3")
    assert rate == pytest.approx(0.90)
    regressions = [r for r in result.reasons if r.startswith("regressed:")]
    assert len(regressions) == 4
    assert result.reasons == regressions
    assert not result.passed


def test_v4_passes_the_gate() -> None:
    rate, result = gate_for("v4")
    assert rate == pytest.approx(0.94)
    assert result.passed, result.reasons


def test_gate_fails_on_missed_urgent_claim() -> None:
    matrix = {"urgent": {"urgent": 8, "standard": 1, "fast_track": 0, "invalid": 0}}
    result = check_gate(0.95, matrix, {}, {})
    assert any("urgent recall" in r for r in result.reasons)


def test_v3_regressions_are_all_fast_track() -> None:
    baseline = majority_pass(evaluate("v2", runs=3).passes_by_case())
    v3 = evaluate("v3", runs=3)
    diff = paired_diff(baseline, majority_pass(v3.passes_by_case()))
    expected = {r.id: r.expected for r in v3.results}
    assert {expected[c] for c in diff.regressed} == {"fast_track"}
