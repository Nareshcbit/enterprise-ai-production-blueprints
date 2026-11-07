"""Calibrate the judge: score its verdicts against the adjusters' grades.

python -m harness.judge_run          # recorded verdicts
python -m harness.judge_run --live   # ask the judge model on Bedrock
"""

from __future__ import annotations

import argparse

from harness import bedrock, preflight
from harness.data import load_calibration, load_judge_recording, load_prompt
from harness.judge import agreement, judge_is_trusted, parse_verdict


def live_verdicts(items: list[dict]) -> dict[str, str]:
    client = bedrock.make_client()
    system = load_prompt("judge")
    return {
        it["id"]: bedrock.call(
            client, bedrock.judge_request(system, it["claim"], it["priority"], it["reason"])
        )
        for it in items
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true")
    args = p.parse_args()
    if args.live:
        preflight.require(["C2"])
    items = load_calibration()
    outputs = live_verdicts(items) if args.live else load_judge_recording()
    grades = {it["id"]: it["adjuster_grade"] for it in items}
    score = agreement(outputs, grades)
    print(f"judge agrees with adjusters on {score:.0%} of {len(grades)} reasons")
    print("judge trusted" if judge_is_trusted(score) else "judge NOT trusted: fix the rubric first")
    if not args.live:
        print(f"C-1042 reason verdict: {parse_verdict(outputs['C-1042'])}")


if __name__ == "__main__":
    main()
