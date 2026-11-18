"""Join each step's per-host transcripts into one: the x86 part first, then the Arm part.

Run: python3 tools/assemble.py recordings/raw
(reads raw/x86/<id>.txt and raw/arm/<id>.txt; writes raw/<id>.txt)
"""

from __future__ import annotations

import sys
from pathlib import Path

HOSTS = ("x86", "arm")


def assemble(raw_dir: Path) -> list[str]:
    step_ids = sorted({p.stem for host in HOSTS for p in (raw_dir / host).glob("*.txt")})
    for step_id in step_ids:
        parts = [(raw_dir / host / f"{step_id}.txt") for host in HOSTS]
        text = "".join(p.read_text() for p in parts if p.is_file())
        (raw_dir / f"{step_id}.txt").write_text(text)
    return step_ids


if __name__ == "__main__":
    print("assembled", " ".join(assemble(Path(sys.argv[1]))))
