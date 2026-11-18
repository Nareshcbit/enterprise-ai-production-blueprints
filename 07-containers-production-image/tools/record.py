"""Run a step file in one bash session and write a transcript.

A step file holds shell commands, one per line; a trailing backslash continues a command and lines
starting with '#' are comments. The transcript has each command as '$ <command>' followed by its
output, exactly as a terminal shows it. The line '# host: <label>' goes after the first command so
every transcript says where it ran. The AWS account ID is replaced with '<account>'.

Run: python3 tools/record.py --host "CodeBuild x86 standard:7.0" --out raw/x86 --cwd work steps/x86/*.sh
"""

from __future__ import annotations

import argparse
import os
import subprocess
import uuid
from pathlib import Path

SENTINEL = "__step_done_" + uuid.uuid4().hex


def read_commands(step_file: Path) -> list[str]:
    commands: list[str] = []
    pending: list[str] = []
    for line in step_file.read_text().splitlines():
        if not pending and (not line.strip() or line.lstrip().startswith("#")):
            continue
        pending.append(line)
        if not line.endswith("\\"):
            commands.append("\n".join(pending))
            pending = []
    if pending:
        commands.append("\n".join(pending))
    return commands


def redact(text: str, account: str) -> str:
    return text.replace(account, "<account>") if account else text


def run_in_session(shell: subprocess.Popen, command: str) -> list[str]:
    assert shell.stdin is not None and shell.stdout is not None
    shell.stdin.write(f"{{\n{command}\n}} < /dev/null 2>&1\necho {SENTINEL}\n")
    shell.stdin.flush()
    lines: list[str] = []
    for line in shell.stdout:
        line = line.rstrip("\n")
        if line.endswith(SENTINEL):  # output without a final newline shares the sentinel's line
            if line != SENTINEL:
                lines.append(line[: -len(SENTINEL)])
            return lines
        lines.append(line)
    raise RuntimeError(f"shell exited while running: {command}")


def record_step(step_file: Path, host: str, cwd: Path, account: str) -> str:
    shell = subprocess.Popen(
        ["bash", "--noprofile", "--norc"],
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    out: list[str] = []
    try:
        for index, command in enumerate(read_commands(step_file)):
            out.append("$ " + command)
            if index == 0:
                out.append(f"# host: {host}")
            out.extend(run_in_session(shell, command))
    finally:
        shell.terminate()
    return redact("\n".join(out) + "\n", account)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", required=True, help="label written as '# host: <label>'")
    parser.add_argument("--out", required=True, type=Path, help="directory for <step>.txt transcripts")
    parser.add_argument("--cwd", required=True, type=Path, help="directory the commands run in")
    parser.add_argument("steps", nargs="+", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    account = os.environ.get("ACCOUNT_ID", "")
    for step_file in args.steps:
        transcript = record_step(step_file, args.host, args.cwd, account)
        (args.out / f"{step_file.stem}.txt").write_text(transcript)
        print(f"recorded {step_file.stem}", flush=True)


if __name__ == "__main__":
    main()
