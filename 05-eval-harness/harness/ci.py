"""CI entry point: evaluate a candidate prompt against the saved baseline and exit 1 to block it.

python -m harness.ci --candidate v4 --baseline baselines/v2.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from harness.gate import check_gate
from harness.metrics import majority_pass
from harness.run import evaluate, matrix_for


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", required=True, choices=["v2", "v3", "v4"])
    p.add_argument("--baseline", required=True, type=Path)
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--live", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    baseline = json.loads(args.baseline.read_text())
    report = evaluate(args.candidate, args.runs, "enum", args.live)
    candidate = majority_pass(report.passes_by_case())
    rate = sum(candidate.values()) / len(candidate)
    result = check_gate(rate, matrix_for(report), baseline, candidate)
    print(f"candidate {args.candidate}: pass rate {rate:.0%} (majority of {args.runs})")
    for reason in result.reasons:
        print(f"  FAIL {reason}")
    print("GATE PASSED" if result.passed else "GATE FAILED")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
