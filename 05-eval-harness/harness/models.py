"""Typed shapes for cases, model outputs and results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

Priority = Literal["urgent", "standard", "fast_track"]
PRIORITIES: tuple[str, ...] = ("urgent", "standard", "fast_track")


class Expected(BaseModel):
    priority: Priority


class Case(BaseModel):
    id: str
    claim: str
    expected: Expected


class Triage(BaseModel):
    """What the assistant must return. Anything else is a failed case."""

    priority: Priority
    reason: str = Field(min_length=1)


class Verdict(BaseModel):
    """What the judge must return for one reason."""

    verdict: Literal["pass", "fail"]
    rule_violated: str | None = None


@dataclass(frozen=True)
class CaseResult:
    id: str
    run: int
    expected: str
    output: str
    passed: bool


@dataclass
class EvalReport:
    prompt: str
    results: list[CaseResult] = field(default_factory=list)

    def run_ids(self) -> list[int]:
        return sorted({r.run for r in self.results})

    def run_pass_rate(self, run: int) -> float:
        rows = [r for r in self.results if r.run == run]
        return sum(r.passed for r in rows) / len(rows)

    def passes_by_case(self) -> dict[str, list[bool]]:
        by_case: dict[str, list[bool]] = {}
        for r in sorted(self.results, key=lambda r: r.run):
            by_case.setdefault(r.id, []).append(r.passed)
        return by_case
