"""Run the eval: grade every case for one prompt version and print a report.

Offline (default) reads recordings/; --live calls Bedrock.

  python -m harness.run --prompt v2 --runs 3 --grader enum --per-class
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Callable
from pathlib import Path

from harness import bedrock, graders, metrics, preflight
from harness.data import LAB_ROOT, load_cases, load_prompt, load_recording
from harness.models import Case, CaseResult, EvalReport

Grader = Callable[[str, str], bool]
GRADERS: dict[str, Grader] = {"string": graders.grade_string, "enum": graders.grade_enum}


def recorded_outputs(prompt: str, cases: list[Case], runs: int) -> dict[tuple[str, int], str]:
    recording = load_recording(prompt)
    return {(c.id, r): recording[(c.id, r)] for c in cases for r in range(runs)}


def live_outputs(prompt: str, cases: list[Case], runs: int) -> dict[tuple[str, int], str]:
    client = bedrock.make_client()
    system = load_prompt(f"triage_{prompt}")
    structured = prompt != "v1"
    outputs = {}
    for case in cases:
        for run in range(runs):
            request = bedrock.triage_request(system, case.claim, structured)
            outputs[(case.id, run)] = bedrock.call(client, request)
    return outputs


def evaluate(prompt: str, runs: int = 1, grader: str = "enum", live: bool = False) -> EvalReport:
    cases = load_cases()
    fetch = live_outputs if live else recorded_outputs
    outputs = fetch(prompt, cases, runs)
    grade = GRADERS[grader]
    report = EvalReport(prompt=prompt)
    for case in cases:
        for run in range(runs):
            out = outputs[(case.id, run)]
            ok = grade(out, case.expected.priority)
            report.results.append(CaseResult(case.id, run, case.expected.priority, out, ok))
    return report


def predicted(output: str) -> str | None:
    try:
        return graders.parse_triage(output).priority
    except ValueError:
        return None


def matrix_for(report: EvalReport, run: int = 0) -> metrics.Matrix:
    pairs = [(r.expected, predicted(r.output)) for r in report.results if r.run == run]
    return metrics.confusion_matrix(pairs)


def print_runs(report: EvalReport) -> None:
    for run in report.run_ids():
        print(f"prompt {report.prompt}  run {run}: pass rate {report.run_pass_rate(run):.0%}")


def print_matrix(matrix: metrics.Matrix) -> None:
    cols = list(next(iter(matrix.values())))
    print("label \\ said".ljust(14) + "".join(c.rjust(12) for c in cols))
    for label, row in matrix.items():
        print(label.ljust(14) + "".join(str(row[c]).rjust(12) for c in cols))
    print(f"urgent recall: {metrics.recall(matrix, 'urgent'):.0%}")


def save_majority(report: EvalReport, path: Path) -> None:
    majority = metrics.majority_pass(report.passes_by_case())
    path.write_text(json.dumps(majority, indent=1, sort_keys=True))
    print(f"saved per-case results to {path}")


def show_case(report: EvalReport, case_id: str) -> None:
    for r in report.results:
        if r.id == case_id:
            print(f"{case_id} run {r.run}: expected {r.expected}  output {r.output!r}  passed {r.passed}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prompt", default="v2", choices=["v1", "v2", "v3", "v4"])
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--grader", default="enum", choices=sorted(GRADERS))
    p.add_argument("--live", action="store_true")
    p.add_argument("--per-class", action="store_true")
    p.add_argument("--majority", action="store_true")
    p.add_argument("--show", metavar="CASE_ID")
    p.add_argument("--save", type=Path, metavar="FILE")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.live:
        preflight.require(["A3", "B2", "B4"])
        logging.basicConfig(filename=LAB_ROOT / "live.log", level=logging.INFO)
    report = evaluate(args.prompt, args.runs, args.grader, args.live)
    print_runs(report)
    if args.show:
        show_case(report, args.show)
    if args.per_class:
        print_matrix(matrix_for(report))
    if args.majority:
        rates = metrics.majority_pass(report.passes_by_case())
        rate = sum(rates.values()) / len(rates)
        moe = metrics.margin_of_error(rate, len(rates))
        print(f"majority of {args.runs}: {rate:.0%} ± {moe:.0%} (95%, n={len(rates)})")
    if args.save:
        save_majority(report, args.save)


if __name__ == "__main__":
    main()
