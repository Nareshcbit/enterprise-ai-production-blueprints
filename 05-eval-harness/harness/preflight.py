"""Stop a live run before its first paid call if a step it needs is still a TODO.

Without this, a live run makes every Bedrock call first and only then hits the unfinished step.
Each probe calls the step's functions once on tiny inputs; NotImplementedError means not done.
"""

from __future__ import annotations

from collections.abc import Callable

from harness import graders, judge, metrics

TRIAGE = '{"priority": "urgent", "reason": "probe"}'
VERDICT = '{"verdict": "pass"}'

PROBES: dict[str, Callable[[], object]] = {
    "A3": lambda: graders.grade_enum(TRIAGE, "urgent"),
    "B2": lambda: metrics.recall(metrics.confusion_matrix([("urgent", "urgent")]), "urgent"),
    "B4": lambda: (metrics.margin_of_error(0.5, 10), metrics.majority_pass({"probe": [True]})),
    "C2": lambda: judge.agreement({"probe": VERDICT}, {"probe": "pass"}),
}


def unfinished(steps: list[str]) -> list[str]:
    """The steps in `steps` whose functions still raise NotImplementedError."""
    todo = []
    for step in steps:
        try:
            PROBES[step]()
        except NotImplementedError:
            todo.append(step)
    return todo


def require(steps: list[str]) -> None:
    """Exit with a message, before any AWS call, unless every step in `steps` is finished."""
    todo = unfinished(steps)
    if todo:
        raise SystemExit(
            f"Live mode needs step(s) {', '.join(todo)} finished first; no Bedrock calls were made.\n"
            "Finish them (make test shows which tests fail), or copy solutions/*.py into harness/."
        )
