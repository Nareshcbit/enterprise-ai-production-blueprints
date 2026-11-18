"""Each Dockerfile passes BuildKit's checks, and the fixed versions keep their fixes."""

import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"
DOCKERFILES = sorted(p for p in (APP / "docker").glob("Dockerfile.*") if p.suffix != ".dockerignore")
CLEAN_DOCKERFILES = [p for p in DOCKERFILES if p.name != "Dockerfile.s1"]  # s1 is the bad example


def docker_running() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def from_lines(name: str) -> list[str]:
    text = (APP / "docker" / f"Dockerfile.{name}").read_text()
    return [line for line in text.splitlines() if line.startswith("FROM ")]


def buildkit_check(dockerfile: Path) -> subprocess.CompletedProcess:
    command = ["docker", "buildx", "build", "--check", "-f", str(dockerfile), str(APP)]
    return subprocess.run(command, capture_output=True, text=True)


needs_docker = pytest.mark.skipif(not docker_running(), reason="needs a running Docker daemon")


@needs_docker
@pytest.mark.parametrize("dockerfile", CLEAN_DOCKERFILES, ids=lambda p: p.name)
def test_buildkit_check_passes(dockerfile: Path) -> None:
    result = buildkit_check(dockerfile)
    assert result.returncode == 0, result.stdout + result.stderr


@needs_docker
def test_buildkit_check_flags_the_build_arg_secret_in_s1() -> None:
    result = buildkit_check(APP / "docker" / "Dockerfile.s1")
    assert result.returncode == 1
    assert "SecretsUsedInArgOrEnv" in result.stdout + result.stderr


@pytest.mark.parametrize("name", ["v3", "v4", "v5", "v6", "v7"])
def test_dockerignore_keeps_secrets_and_git_out(name: str) -> None:
    ignored = (APP / "docker" / f"Dockerfile.{name}.dockerignore").read_text().split()
    assert {".git", "target", ".env", "settings.xml"} <= set(ignored)


def test_v7_pins_every_base_by_digest() -> None:
    assert all("@sha256:" in line for line in from_lines("v7"))


@pytest.mark.parametrize("name", ["v6", "v7"])
def test_runtime_stage_is_distroless_nonroot(name: str) -> None:
    assert "gcr.io/distroless/java21-debian13:nonroot" in from_lines(name)[-1]


def test_secret_mount_replaces_the_build_arg() -> None:
    s3 = (APP / "docker" / "Dockerfile.s3").read_text()
    assert "--mount=type=secret,id=repo_token" in s3 and "ARG" not in s3
