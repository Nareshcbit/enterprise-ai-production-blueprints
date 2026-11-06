"""Metrics that say what a pass rate hides."""

from __future__ import annotations

from dataclasses import dataclass

Matrix = dict[str, dict[str, int]]


def confusion_matrix(pairs: list[tuple[str, str | None]]) -> Matrix:
    """Step B2: rows are the label, columns what the assistant said (None = unparseable).

    Rows: urgent, standard, fast_track. Columns: the same three plus "invalid".
    """
    raise NotImplementedError("Step B2: implement confusion_matrix")


def recall(matrix: Matrix, label: str) -> float:
    """Step B2: of the cases labelled `label`, the share the assistant also called `label`."""
    raise NotImplementedError("Step B2: implement recall")


def margin_of_error(rate: float, n: int, z: float = 1.96) -> float:
    """Step B4: 95% margin of error of a pass rate measured on n cases (normal approximation).

    z * sqrt(p * (1 - p) / n)
    """
    raise NotImplementedError("Step B4: implement margin_of_error")


def majority_pass(passes_by_case: dict[str, list[bool]]) -> dict[str, bool]:
    """Step B4: a case passes when it passes in more than half of its runs."""
    raise NotImplementedError("Step B4: implement majority_pass")


@dataclass(frozen=True)
class PairedDiff:
    fixed: list[str]
    regressed: list[str]


def paired_diff(baseline: dict[str, bool], candidate: dict[str, bool]) -> PairedDiff:
    """Step B4: compare case by case, not totals.

    fixed: failed in baseline, passes in candidate. regressed: passed in baseline, fails now.
    Return both lists sorted.
    """
    raise NotImplementedError("Step B4: implement paired_diff")
