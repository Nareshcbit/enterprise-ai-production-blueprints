"""The CI gate: exit 1 when the candidate prompt must not ship.

Caveat: majority-of-3 is a teaching simplification. A case that passes 60% of the time passes a
majority of 3 runs only about 65% of the time, so in live mode a flaky case can "regress" with no
prompt change at all. Rerun a blocked case, or average more runs per case, before you trust a block.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from harness.metrics import paired_diff, recall


@dataclass(frozen=True)
class GateConfig:
    min_pass_rate: float = 0.90
    min_urgent_recall: float = 1.0


DEFAULT_GATE = GateConfig()


@dataclass
class GateResult:
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.reasons


def check_gate(
    pass_rate: float,
    matrix: dict[str, dict[str, int]],
    baseline: dict[str, bool],
    candidate: dict[str, bool],
    config: GateConfig = DEFAULT_GATE,
) -> GateResult:
    """Step D2: fail on a low pass rate, any missed urgent claim, or any per-case regression."""
    result = GateResult()
    if pass_rate < config.min_pass_rate:
        result.reasons.append(f"pass rate {pass_rate:.0%} < {config.min_pass_rate:.0%}")
    urgent = recall(matrix, "urgent")
    if urgent < config.min_urgent_recall:
        result.reasons.append(f"urgent recall {urgent:.0%} < {config.min_urgent_recall:.0%}")
    for case_id in paired_diff(baseline, candidate).regressed:
        result.reasons.append(f"regressed: {case_id}")
    return result
