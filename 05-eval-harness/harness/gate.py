"""The CI gate: exit 1 when the candidate prompt must not ship.

Caveat: majority-of-3 is a teaching simplification. A case that passes 60% of the time passes a
majority of 3 runs only about 65% of the time, so in live mode a flaky case can "regress" with no
prompt change at all. Rerun a blocked case, or average more runs per case, before you trust a block.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
    """Step D2: fail on a low pass rate, any missed urgent claim, or any per-case regression.

    Add one human-readable string to `reasons` per failure, e.g. "regressed: C-1007".
    Use recall() and paired_diff() from harness.metrics.
    """
    raise NotImplementedError("Step D2: implement check_gate")
