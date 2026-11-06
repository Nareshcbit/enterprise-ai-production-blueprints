"""Generate the lab's synthetic claims, labels and recorded model outputs.

Everything in data/ and recordings/ is SYNTHETIC: written by this script, not by a
real insurer or a real model. The recordings are shaped so the lab reproduces the
walkthrough's numbers exactly and offline. Run `make live` to see what a real model does.

Usage: python tools/generate_synthetic.py   (rewrites data/ and recordings/)
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = 1042

URGENT_TEXTS = [
    (
        "A pipe burst under the upstairs bathroom overnight. Water came through the kitchen ceiling "
        "and the bedrooms are soaked. The family of four is staying with a neighbour tonight.",
        "uninhabitable_home",
        18400,
    ),
    (
        "A kitchen fire spread to the living room. The fire service says the house is not safe "
        "to enter. The policyholder and two children are in a hotel.",
        "uninhabitable_home",
        52000,
    ),
    (
        "A tree fell on the car while the driver was inside. The driver was taken to hospital "
        "with a broken arm.",
        "injury",
        9300,
    ),
    (
        "The roof is leaking into the loft and water is still coming in during the storm. "
        "The policyholder cannot reach a roofer until next week.",
        "ongoing_damage",
        7600,
    ),
    (
        "The boiler failed in January. The policyholder is 87, lives alone and has no heating.",
        "vulnerable_customer",
        2900,
    ),
    ("A delivery van hit the front wall and the cyclist on the pavement was injured.", "injury", 14100),
    (
        "The basement is flooding from a broken water main and the water is still rising.",
        "ongoing_damage",
        11800,
    ),
    (
        "Storm damage tore off part of the roof. The council has told the family not to sleep in the house.",
        "uninhabitable_home",
        23500,
    ),
    (
        "A carer reports that the policyholder, who uses a wheelchair, cannot leave the flat "
        "since the lift was damaged in a fire.",
        "vulnerable_customer",
        4200,
    ),
]

STANDARD_TEMPLATES = [
    "Rear bumper dented in a car park. No one was hurt. Estimated repair ${amt}.",
    "Bike stolen from a locked shed. The shed door was forced. Value ${amt}.",
    "Side window broken during an attempted break-in. Nothing taken. Glazier quote ${amt}.",
    "Laptop dropped and the screen cracked. Repair quote ${amt}.",
    "Hail dented the car bonnet and roof. Body shop estimate ${amt}.",
    "Fence panels blown down in high wind. Contractor quote ${amt}.",
    "Washing machine leaked and damaged the kitchen floor. The leak is fixed. Quote ${amt}.",
    "Garage door hit while reversing. Door still works. Estimate ${amt}.",
]

FAST_TRACK_TEMPLATES = [
    "Phone screen cracked. Repair receipt ${amt} attached.",
    "Windscreen chip from a stone on the motorway. Repair ${amt}.",
    "Sunglasses lost on holiday. Receipt ${amt}.",
    "Wing mirror knocked off on a narrow street. Part and fitting ${amt}.",
    "Spoiled food after a two-hour power cut. Receipts total ${amt}.",
]


@dataclass(frozen=True)
class Case:
    id: str
    claim: str
    expected: str
    rule: str | None


def build_cases(rng: random.Random) -> list[Case]:
    """9 urgent (C-1042 is the burst pipe), 70 standard, 21 fast_track, shuffled into ids."""
    urgent = [(text, rule) for text, rule, _ in URGENT_TEXTS]
    standard = [
        STANDARD_TEMPLATES[i % len(STANDARD_TEMPLATES)].replace("{amt}", str(rng.randrange(1200, 6000, 50)))
        for i in range(70)
    ]
    fast = [
        FAST_TRACK_TEMPLATES[i % len(FAST_TRACK_TEMPLATES)].replace("{amt}", str(rng.randrange(40, 900, 5)))
        for i in range(21)
    ]
    ids = [f"C-{n}" for n in range(1001, 1101)]
    others = [i for i in ids if i != "C-1042"]
    rng.shuffle(others)
    cases = [Case("C-1042", urgent[0][0], "urgent", urgent[0][1])]
    pool = (
        [(t, "urgent", r) for t, r in urgent[1:]]
        + [(t, "standard", None) for t in standard]
        + [(t, "fast_track", None) for t in fast]
    )
    rng.shuffle(pool)
    cases += [Case(cid, text, label, rule) for cid, (text, label, rule) in zip(others, pool, strict=True)]
    return sorted(cases, key=lambda c: c.id)


def wrong_label(expected: str) -> str:
    return {"urgent": "standard", "standard": "fast_track", "fast_track": "standard"}[expected]


def assign_v2_groups(cases: list[Case], rng: random.Random) -> dict[str, str]:
    """Per-case correctness pattern for prompt v2 over 3 runs.

    stable (3/3 right) 68, two_of_three 6, one_of_three 8, never 18.
    Urgent: C-1042 and 2 others never right; 6 stable.
    Run totals come out 74, 79, 71; majority-of-3 pass rate 74.
    """
    urgent = [c.id for c in cases if c.expected == "urgent"]
    rest = [c.id for c in cases if c.expected != "urgent"]
    rng.shuffle(rest)
    never_urgent = ["C-1042"] + [u for u in urgent if u != "C-1042"][:2]
    stable_urgent = [u for u in urgent if u not in never_urgent]
    groups = {u: "never" for u in never_urgent} | {u: "stable" for u in stable_urgent}
    for cid in rest[:62]:
        groups[cid] = "stable"
    for cid in rest[62:68]:
        groups[cid] = "two_of_three"
    for cid in rest[68:76]:
        groups[cid] = "one_of_three"
    for cid in rest[76:]:
        groups[cid] = "never"
    return groups


def v2_correct_runs(groups: dict[str, str]) -> dict[str, set[int]]:
    """Which of runs 0,1,2 each case is right in, so run totals are 74 / 79 / 71."""
    two = sorted(c for c, g in groups.items() if g == "two_of_three")
    one = sorted(c for c, g in groups.items() if g == "one_of_three")
    runs: dict[str, set[int]] = {}
    for cid, g in groups.items():
        runs[cid] = {0, 1, 2} if g == "stable" else set()
    for i, cid in enumerate(two):  # all in run 1; 4 also in run 0, 2 also in run 2
        runs[cid] = {1, 0} if i < 4 else {1, 2}
    for i, cid in enumerate(one):  # 2 in run 0, 5 in run 1, 1 in run 2
        runs[cid] = {0} if i < 2 else ({1} if i < 7 else {2})
    return runs


def reason_for(case: Case, predicted: str) -> str:
    if case.id == "C-1042" and predicted != "urgent":
        return "Standard: no injury reported; water damage to kitchen and bedrooms."
    if predicted == "urgent":
        return f"Urgent: {case.rule.replace('_', ' ') if case.rule else 'high risk'}."
    if predicted == "fast_track":
        return "Fast track: small, documented loss with no risk factors."
    return "Standard: property damage with no injury or displacement."


FREE_TEXT_STYLES = {
    "urgent": ["Urgent.", "Priority: urgent", "URGENT - send help today"],
    "standard": ["Standard", "Priority: standard", "standard."],
    "fast_track": ["fast-track", "Fast track", "Priority: fast_track"],
}


def free_text(predicted: str, exact: bool, rng: random.Random) -> str:
    return predicted if exact else rng.choice(FREE_TEXT_STYLES[predicted])


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def v1_rows(cases: list[Case], correct0: dict[str, bool], rng: random.Random) -> list[dict]:
    """Free-text outputs with run-0 decisions; exactly 58 match the label character for character."""
    right = [c.id for c in cases if correct0[c.id]]
    exact_ids = set(sorted(right)[:58])
    rows = []
    for c in cases:
        predicted = c.expected if correct0[c.id] else wrong_label(c.expected)
        rows.append({"id": c.id, "run": 0, "output": free_text(predicted, c.id in exact_ids, rng)})
    return rows


def structured_rows(cases: list[Case], right_in: dict[str, set[int]], runs: int) -> list[dict]:
    rows = []
    for run in range(runs):
        for c in cases:
            predicted = c.expected if run in right_in[c.id] else wrong_label(c.expected)
            out = {"priority": predicted, "reason": reason_for(c, predicted)}
            rows.append({"id": c.id, "run": run, "output": json.dumps(out)})
    return rows


def later_prompt_correct(
    cases: list[Case], v2_majority: dict[str, bool], rng: random.Random
) -> tuple[dict[str, bool], dict[str, bool]]:
    """v3: fixes 20 failing cases (all urgent misses) but breaks 4 passing fast_track: 90%.
    v4: v3 plus the 4 restored: 94%."""
    failing = [c for c in cases if not v2_majority[c.id]]
    urgent_fail = [c.id for c in failing if c.expected == "urgent"]
    other_fail = sorted(c.id for c in failing if c.expected != "urgent")
    rng.shuffle(other_fail)
    fixed = set(urgent_fail + other_fail[:17])
    passing_fast = sorted(c.id for c in cases if v2_majority[c.id] and c.expected == "fast_track")
    broken = set(passing_fast[:4])
    v3 = {c.id: (v2_majority[c.id] or c.id in fixed) and c.id not in broken for c in cases}
    v4 = {c.id: v2_majority[c.id] or c.id in fixed for c in cases}
    return v3, v4


def judge_rows() -> tuple[list[dict], list[dict]]:
    """25 reasons graded by adjusters + the judge's recorded verdicts (22 agree: 88%)."""
    items = []
    for i in range(25):
        bad = i % 3 == 0
        items.append(
            {
                "id": f"J-{i + 1:02d}",
                "claim": URGENT_TEXTS[0][0],
                "priority": "standard" if bad else "urgent",
                "reason": (
                    "Standard: no injury reported." if bad else "Urgent: the home cannot be lived in tonight."
                ),
                "claim_rule": "uninhabitable_home",
                "adjuster_grade": "fail" if bad else "pass",
            }
        )
    disagree = {"J-05", "J-11", "J-20"}
    verdicts = []
    for it in items:
        verdict = it["adjuster_grade"]
        if it["id"] in disagree:
            verdict = "pass" if verdict == "fail" else "fail"
        rule = "uninhabitable_home" if verdict == "fail" else None
        verdicts.append({"id": it["id"], "output": json.dumps({"verdict": verdict, "rule_violated": rule})})
    verdicts.append(
        {"id": "C-1042", "output": json.dumps({"verdict": "fail", "rule_violated": "uninhabitable_home"})}
    )
    return items, verdicts


def main() -> None:
    rng = random.Random(SEED)
    cases = build_cases(rng)
    write_jsonl(
        ROOT / "data/cases.jsonl",
        [{"id": c.id, "claim": c.claim, "expected": {"priority": c.expected}} for c in cases],
    )
    groups = assign_v2_groups(cases, rng)
    right_in = v2_correct_runs(groups)
    correct0 = {cid: 0 in r for cid, r in right_in.items()}
    write_jsonl(ROOT / "recordings/triage_v1.jsonl", v1_rows(cases, correct0, rng))
    write_jsonl(ROOT / "recordings/triage_v2.jsonl", structured_rows(cases, right_in, 3))
    majority = {cid: len(r) >= 2 for cid, r in right_in.items()}
    v3, v4 = later_prompt_correct(cases, majority, rng)
    for name, correct in (("v3", v3), ("v4", v4)):
        runs = {cid: ({0, 1, 2} if ok else set()) for cid, ok in correct.items()}
        write_jsonl(ROOT / f"recordings/triage_{name}.jsonl", structured_rows(cases, runs, 3))
    items, verdicts = judge_rows()
    write_jsonl(ROOT / "data/judge_calibration.jsonl", items)
    write_jsonl(ROOT / "recordings/judge.jsonl", verdicts)


if __name__ == "__main__":
    main()
