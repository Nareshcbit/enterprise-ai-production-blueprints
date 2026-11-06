"""Metrics that say what a pass rate hides."""

from __future__ import annotations

import math
from dataclasses import dataclass

from harness.models import PRIORITIES

Matrix = dict[str, dict[str, int]]


def confusion_matrix(pairs: list[tuple[str, str | None]]) -> Matrix:
    """Step B2: rows are the label, columns what the assistant said (None = unparseable)."""
    columns = [*PRIORITIES, "invalid"]
    matrix: Matrix = {label: {col: 0 for col in columns} for label in PRIORITIES}
    for expected, predicted in pairs:
        matrix[expected][predicted or "invalid"] += 1
    return matrix


def recall(matrix: Matrix, label: str) -> float:
    """Step B2: of the cases labelled `label`, the share the assistant also called `label`."""
    row = matrix[label]
    total = sum(row.values())
    return row[label] / total if total else 0.0


def margin_of_error(rate: float, n: int, z: float = 1.96) -> float:
    """Step B4: 95% margin of error of a pass rate measured on n cases (normal approximation)."""
    return z * math.sqrt(rate * (1 - rate) / n)


def majority_pass(passes_by_case: dict[str, list[bool]]) -> dict[str, bool]:
    """Step B4: a case passes when it passes in more than half of its runs."""
    return {cid: sum(runs) * 2 > len(runs) for cid, runs in passes_by_case.items()}


@dataclass(frozen=True)
class PairedDiff:
    fixed: list[str]
    regressed: list[str]


def paired_diff(baseline: dict[str, bool], candidate: dict[str, bool]) -> PairedDiff:
    """Step B4: compare case by case, not totals."""
    fixed = sorted(c for c in candidate if candidate[c] and not baseline.get(c, False))
    regressed = sorted(c for c in candidate if baseline.get(c, False) and not candidate[c])
    return PairedDiff(fixed=fixed, regressed=regressed)
