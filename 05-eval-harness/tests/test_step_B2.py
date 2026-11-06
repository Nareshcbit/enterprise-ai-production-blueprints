"""Step B2: a per-class confusion matrix; gate on urgent recall, not overall accuracy."""

import pytest

from harness.metrics import confusion_matrix, recall
from harness.run import evaluate, matrix_for


def test_matrix_counts_label_against_prediction() -> None:
    m = confusion_matrix([("urgent", "urgent"), ("urgent", "standard"), ("standard", None)])
    assert m["urgent"] == {"urgent": 1, "standard": 1, "fast_track": 0, "invalid": 0}
    assert m["standard"]["invalid"] == 1


def test_recall_is_share_of_label_caught() -> None:
    m = confusion_matrix([("urgent", "urgent"), ("urgent", "standard")])
    assert recall(m, "urgent") == pytest.approx(0.5)


def test_v2_catches_only_6_of_9_urgent_claims() -> None:
    m = matrix_for(evaluate("v2"))
    assert sum(m["urgent"].values()) == 9
    assert m["urgent"]["urgent"] == 6
    assert m["urgent"]["standard"] == 3
