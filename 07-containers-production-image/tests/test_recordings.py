"""Every step has a make target and a transcript that starts with a command and names its host."""

import re
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parent.parent
STEPS = re.search(r"^STEPS = (.*?)\n\n", (LAB / "Makefile").read_text(), re.S | re.M).group(1)
STEP_IDS = STEPS.replace("\\", " ").split()
ACCOUNT_ID = re.compile(r"(?<![0-9a-f])\d{12}(?![0-9a-f])")


def recording(step_id: str) -> list[str]:
    return (LAB / "recordings" / f"{step_id}.txt").read_text().splitlines()


def test_all_seventeen_steps_are_listed() -> None:
    assert len(STEP_IDS) == 17


@pytest.mark.parametrize("step_id", STEP_IDS)
def test_step_has_make_target(step_id: str) -> None:
    assert re.search(rf"^{re.escape(step_id)}:\s+## ", (LAB / "Makefile").read_text(), re.M)


@pytest.mark.parametrize("step_id", STEP_IDS)
def test_recording_starts_with_a_command_then_the_host(step_id: str) -> None:
    lines = recording(step_id)
    assert lines[0].startswith("$ ")
    after_first_command = 1
    while lines[after_first_command - 1].endswith("\\"):
        after_first_command += 1
    assert lines[after_first_command].startswith("# host: CodeBuild ")


@pytest.mark.parametrize("step_id", STEP_IDS)
def test_trimmed_recording_only_cuts_whole_lines_from_the_raw_one(step_id: str) -> None:
    raw = (LAB / "recordings" / "raw" / f"{step_id}.txt").read_text().splitlines()
    position = 0
    for line in recording(step_id):
        if line == "…":
            continue
        assert line in raw[position:], f"{step_id}: not in raw, or out of order: {line!r}"
        position = raw.index(line, position) + 1


@pytest.mark.parametrize("path", sorted((LAB / "recordings").rglob("*.txt")), ids=lambda p: p.name)
def test_no_account_id_in_recordings(path: Path) -> None:
    assert not ACCOUNT_ID.search(path.read_text()), f"unredacted 12-digit number in {path.name}"
