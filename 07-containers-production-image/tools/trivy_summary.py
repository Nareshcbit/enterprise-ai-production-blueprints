"""Summarise Trivy JSON reports: findings per image, split into OS packages and Java libraries.

Run: python3 tools/trivy_summary.py scan-v3.json scan-v4.json scan-v5.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageFindings:
    image: str
    os_findings: int
    os_packages: int
    lang_findings: int
    severities: Counter

    @property
    def total(self) -> int:
        return self.os_findings + self.lang_findings


def summarise(report: dict) -> ImageFindings:
    os_findings = lang_findings = 0
    os_packages: set[str] = set()
    severities: Counter = Counter()
    for result in report.get("Results", []):
        vulns = result.get("Vulnerabilities") or []
        severities.update(v["Severity"] for v in vulns)
        if result.get("Class") == "os-pkgs":
            os_findings += len(vulns)
            os_packages.update(v["PkgName"] for v in vulns)
        else:
            lang_findings += len(vulns)
    image = report.get("ArtifactName", "?")
    return ImageFindings(image, os_findings, len(os_packages), lang_findings, severities)


def format_rows(rows: list[ImageFindings]) -> str:
    header = f"{'image':<8}{'total':>7}{'os':>6}{'os-pkgs':>9}{'java':>6}"
    header += f"{'CRIT':>6}{'HIGH':>6}{'MED':>6}{'LOW':>6}"
    lines = [header]
    for row in rows:
        sev = row.severities
        lines.append(
            f"{row.image:<8}{row.total:>7}{row.os_findings:>6}{row.os_packages:>9}{row.lang_findings:>6}"
            f"{sev['CRITICAL']:>6}{sev['HIGH']:>6}{sev['MEDIUM']:>6}{sev['LOW']:>6}"
        )
    return "\n".join(lines)


def main(paths: list[str]) -> None:
    rows = [summarise(json.loads(Path(p).read_text())) for p in paths]
    print(format_rows(rows))


if __name__ == "__main__":
    main(sys.argv[1:])
