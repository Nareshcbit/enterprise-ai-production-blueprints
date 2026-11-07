"""Live mode guards: a default region, and no paid calls while a needed step is unfinished."""

import pytest

from harness import bedrock, graders, judge, metrics, preflight


def not_done(*_args: object, **_kwargs: object) -> None:
    raise NotImplementedError("Step X: not done")


def finish_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graders, "grade_enum", lambda output, expected: True)
    monkeypatch.setattr(metrics, "confusion_matrix", lambda pairs: {})
    monkeypatch.setattr(metrics, "recall", lambda matrix, label: 1.0)
    monkeypatch.setattr(metrics, "margin_of_error", lambda rate, n: 0.0)
    monkeypatch.setattr(metrics, "majority_pass", lambda passes: {})
    monkeypatch.setattr(judge, "agreement", lambda outputs, grades: 1.0)


def test_region_defaults_to_us_east_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    assert bedrock.region() == "us-east-1"


def test_region_follows_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    assert bedrock.region() == "eu-west-1"
    monkeypatch.delenv("AWS_REGION")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-2")
    assert bedrock.region() == "ap-southeast-2"


def test_finished_steps_pass_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    finish_everything(monkeypatch)
    assert preflight.unfinished(["A3", "B2", "B4", "C2"]) == []
    preflight.require(["A3", "B2", "B4", "C2"])


def test_unfinished_step_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    finish_everything(monkeypatch)
    monkeypatch.setattr(graders, "grade_enum", not_done)
    monkeypatch.setattr(judge, "agreement", not_done)
    assert preflight.unfinished(["A3", "B2", "B4", "C2"]) == ["A3", "C2"]


def test_require_stops_before_any_call(monkeypatch: pytest.MonkeyPatch) -> None:
    finish_everything(monkeypatch)
    monkeypatch.setattr(metrics, "majority_pass", not_done)
    with pytest.raises(SystemExit, match="B4"):
        preflight.require(["A3", "B4"])
