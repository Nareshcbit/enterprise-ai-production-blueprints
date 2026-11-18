"""The recorder, the transcript joiner and the Trivy summary."""

from collections import Counter
from pathlib import Path

from tools.assemble import assemble
from tools.record import read_commands, record_step, redact
from tools.trivy_summary import format_rows, summarise


def test_read_commands_joins_continuations_and_skips_comments(tmp_path: Path) -> None:
    step = tmp_path / "s.sh"
    step.write_text("# a comment\necho one\n\nfor i in 1 2; do \\\n  echo $i; \\\ndone\n")
    assert read_commands(step) == ["echo one", "for i in 1 2; do \\\n  echo $i; \\\ndone"]


def test_record_step_keeps_shell_state_and_adds_the_host_line(tmp_path: Path) -> None:
    step = tmp_path / "s.sh"
    step.write_text("export X=111122223333\necho $X done\n")
    transcript = record_step(step, "test host", tmp_path, account="111122223333")
    expected = ["$ export X=<account>", "# host: test host", "$ echo $X done", "<account> done"]
    assert transcript.splitlines() == expected


def test_record_step_handles_output_without_a_final_newline(tmp_path: Path) -> None:
    step = tmp_path / "s.sh"
    step.write_text("printf abc\necho next\n")
    lines = record_step(step, "h", tmp_path, account="").splitlines()
    assert lines == ["$ printf abc", "# host: h", "abc", "$ echo next", "next"]


def test_redact_without_account_is_a_no_op() -> None:
    assert redact("abc", "") == "abc"


def test_assemble_puts_x86_before_arm(tmp_path: Path) -> None:
    for host, text in (("x86", "$ a\n"), ("arm", "$ b\n")):
        (tmp_path / host).mkdir()
        (tmp_path / host / "multiarch.txt").write_text(text)
    assert assemble(tmp_path) == ["multiarch"]
    assert (tmp_path / "multiarch.txt").read_text() == "$ a\n$ b\n"


REPORT = {
    "ArtifactName": "pf:v4",
    "Results": [
        {
            "Class": "os-pkgs",
            "Vulnerabilities": [
                {"PkgName": "libc6", "Severity": "HIGH"},
                {"PkgName": "libc6", "Severity": "LOW"},
            ],
        },
        {"Class": "lang-pkgs", "Type": "jar", "Vulnerabilities": [{"PkgName": "j", "Severity": "CRITICAL"}]},
        {"Class": "lang-pkgs", "Type": "jar"},
    ],
}


def test_summarise_splits_os_and_java_findings() -> None:
    row = summarise(REPORT)
    assert (row.total, row.os_findings, row.os_packages, row.lang_findings) == (3, 2, 1, 1)
    assert row.severities == Counter({"HIGH": 1, "LOW": 1, "CRITICAL": 1})


def test_format_rows_has_a_header_and_one_line_per_image() -> None:
    lines = format_rows([summarise(REPORT)]).splitlines()
    assert lines[0].split() == ["image", "total", "os", "os-pkgs", "java", "CRIT", "HIGH", "MED", "LOW"]
    assert lines[1].split() == ["pf:v4", "3", "2", "1", "1", "1", "1", "0", "1"]
