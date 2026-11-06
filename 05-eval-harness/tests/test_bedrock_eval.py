"""Bedrock Evaluations request and dataset, checked offline with stub clients (no AWS call)."""

import json
from pathlib import Path
from typing import Any

import botocore.session
from botocore.validate import validate_parameters

from harness import bedrock_eval
from harness.data import load_prompt

CONFIG = bedrock_eval.JobConfig(
    role_arn="arn:aws:iam::111122223333:role/BedrockEvalRole",
    bucket="my-eval-bucket",
    prefix="eval-harness",
    judge_model_id="us.anthropic.claude-opus-4-5-20251101-v1:0",
    region="us-east-1",
    job_name="eval-harness-v2-test",
)


class StubS3:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, str]] = []

    def upload_file(self, Filename: str, Bucket: str, Key: str) -> None:  # noqa: N803 (boto3 names)
        self.uploads.append((Filename, Bucket, Key))


class StubBedrock:
    def __init__(self) -> None:
        self.request: dict[str, Any] = {}

    def create_evaluation_job(self, **kwargs: Any) -> dict[str, Any]:
        self.request = kwargs
        return {"jobArn": "arn:aws:bedrock:us-east-1:111122223333:evaluation-job/abc123"}


def test_dataset_rows_have_the_documented_fields() -> None:
    rows = bedrock_eval.dataset_rows()
    assert len(rows) == 100
    for row in rows:
        assert set(row) == {"prompt", "referenceResponse", "category", "modelResponses"}
        assert len(row["modelResponses"]) == 1
        assert row["modelResponses"][0]["modelIdentifier"] == bedrock_eval.MODEL_IDENTIFIER


def test_c1042_carries_its_reference_and_recorded_response() -> None:
    row = next(r for r in bedrock_eval.dataset_rows() if "pipe burst" in r["prompt"])
    assert row["referenceResponse"] == "urgent"
    assert row["category"] == "urgent"
    response = json.loads(row["modelResponses"][0]["response"])
    assert response["priority"] == "standard"
    assert "no injury reported" in response["reason"]


def test_write_dataset_is_one_json_object_per_line(tmp_path: Path) -> None:
    path = bedrock_eval.write_dataset(tmp_path / "byo.jsonl")
    lines = path.read_text().splitlines()
    assert len(lines) == 100
    assert all(json.loads(line)["modelResponses"] for line in lines)


def test_custom_metric_applies_the_judge_rubric() -> None:
    metric = bedrock_eval.custom_metric(load_prompt("judge"))["customMetricDefinition"]
    for rule in ("uninhabitable_home", "injury", "ongoing_damage", "vulnerable_customer"):
        assert rule in metric["instructions"]
    assert "record_verdict" not in metric["instructions"]
    assert metric["instructions"].rstrip().endswith("{{prediction}}")
    assert "{{prompt}}" in metric["instructions"]
    assert [s["definition"] for s in metric["ratingScale"]] == ["Pass", "Fail"]


def test_request_uses_custom_metric_and_precomputed_inference() -> None:
    req = bedrock_eval.job_request(CONFIG, load_prompt("judge"))
    automated = req["evaluationConfig"]["automated"]
    custom = automated["customMetricConfig"]
    assert automated["datasetMetricConfigs"][0]["metricNames"] == [bedrock_eval.METRIC_NAME]
    assert custom["customMetrics"][0]["customMetricDefinition"]["name"] == bedrock_eval.METRIC_NAME
    assert custom["evaluatorModelConfig"]["bedrockEvaluatorModels"][0]["modelIdentifier"] == (
        CONFIG.judge_model_id
    )
    source = req["inferenceConfig"]["models"][0]["precomputedInferenceSource"]
    assert source == {"inferenceSourceIdentifier": bedrock_eval.MODEL_IDENTIFIER}
    assert req["applicationType"] == "ModelEvaluation"
    assert req["roleArn"] == CONFIG.role_arn


def test_request_matches_the_botocore_model() -> None:
    model = botocore.session.get_session().get_service_model("bedrock")
    shape = model.operation_model("CreateEvaluationJob").input_shape
    validate_parameters(bedrock_eval.job_request(CONFIG, load_prompt("judge")), shape)


def test_submit_uploads_then_creates_the_job(tmp_path: Path) -> None:
    s3, client = StubS3(), StubBedrock()
    dataset = bedrock_eval.write_dataset(tmp_path / "byo.jsonl")
    arn = bedrock_eval.submit(CONFIG, dataset, s3, client)
    assert s3.uploads == [(str(dataset), "my-eval-bucket", "eval-harness/input/triage_v2_byo.jsonl")]
    location = client.request["evaluationConfig"]["automated"]["datasetMetricConfigs"][0]["dataset"]
    assert (
        location["datasetLocation"]["s3Uri"] == "s3://my-eval-bucket/eval-harness/input/triage_v2_byo.jsonl"
    )
    assert client.request["outputDataConfig"]["s3Uri"] == "s3://my-eval-bucket/eval-harness/output/"
    assert arn.endswith("evaluation-job/abc123")
