"""Same data on Amazon Bedrock Evaluations: grade the recorded v2 outputs with a managed judge.

python -m harness.bedrock_eval            # dry run (default): write the dataset, print the request
python -m harness.bedrock_eval --submit   # upload the dataset to S3 and start the job (costs money)

The job brings its own inference responses (precomputedInferenceSource), so Bedrock does not call
the triage model; it only runs the judge. The custom metric reuses the rubric in prompts/judge.md.
Docs: https://docs.aws.amazon.com/bedrock/latest/userguide/evaluation-judge.html
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from harness.data import LAB_ROOT, load_cases, load_prompt, load_recording

PROMPT_VERSION = "v2"
MODEL_IDENTIFIER = "triage-v2"
METRIC_NAME = "UrgentRulesReason"
DATASET_NAME = "triage-v2-byo"
DATASET_FILE = "triage_v2_byo.jsonl"
LOCAL_DATASET = LAB_ROOT / "bedrock_eval" / DATASET_FILE
RUBRIC_END = "Reply only by"
PLACEHOLDER_ROLE = "arn:aws:iam::111122223333:role/BedrockEvalRole"
PLACEHOLDER_BUCKET = "amzn-s3-demo-bucket"

SCALE_GUIDE = """Rate the reason on this scale:
- Pass: the reason respects every urgent rule
- Fail: the reason ignores a fact that triggers an urgent rule"""

TASK_VARIABLES = """Here is the actual task:
Claim: {{prompt}}
Triage output (priority and reason): {{prediction}}"""

log = logging.getLogger("harness.bedrock_eval")


class JobConfig(BaseModel):
    role_arn: str
    bucket: str
    prefix: str
    judge_model_id: str
    region: str
    job_name: str

    def dataset_key(self) -> str:
        return f"{self.prefix}/input/{DATASET_FILE}"

    def dataset_uri(self) -> str:
        return f"s3://{self.bucket}/{self.dataset_key()}"

    def output_uri(self) -> str:
        return f"s3://{self.bucket}/{self.prefix}/output/"


class S3Client(Protocol):
    def upload_file(self, Filename: str, Bucket: str, Key: str) -> None: ...  # noqa: N803


class EvaluationClient(Protocol):
    def create_evaluation_job(self, **kwargs: Any) -> dict[str, Any]: ...


def dataset_rows() -> list[dict[str, Any]]:
    """One BYO-response row per case: the claim, the adjusters' label and recorded run 0."""
    recording = load_recording(PROMPT_VERSION)
    return [
        {
            "prompt": case.claim,
            "referenceResponse": case.expected.priority,
            "category": case.expected.priority,
            "modelResponses": [{"response": recording[(case.id, 0)], "modelIdentifier": MODEL_IDENTIFIER}],
        }
        for case in load_cases()
    ]


def write_dataset(path: Path = LOCAL_DATASET) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in dataset_rows()))
    return path


def rubric_text(judge_prompt: str) -> str:
    """The rubric from prompts/judge.md, without the record_verdict tool instruction."""
    if RUBRIC_END not in judge_prompt:
        raise ValueError(f"judge prompt has no '{RUBRIC_END}' line to cut at")
    return judge_prompt.split(RUBRIC_END)[0].rstrip()


def custom_metric(judge_prompt: str) -> dict[str, Any]:
    instructions = f"{rubric_text(judge_prompt)}\n\n{SCALE_GUIDE}\n\n{TASK_VARIABLES}"
    scale = [
        {"definition": "Pass", "value": {"floatValue": 1.0}},
        {"definition": "Fail", "value": {"floatValue": 0.0}},
    ]
    return {
        "customMetricDefinition": {
            "name": METRIC_NAME,
            "instructions": instructions,
            "ratingScale": scale,
        }
    }


def evaluator(model_id: str) -> dict[str, Any]:
    return {"bedrockEvaluatorModels": [{"modelIdentifier": model_id}]}


def automated_config(config: JobConfig, judge_prompt: str) -> dict[str, Any]:
    dataset = {"name": DATASET_NAME, "datasetLocation": {"s3Uri": config.dataset_uri()}}
    return {
        "datasetMetricConfigs": [{"taskType": "General", "dataset": dataset, "metricNames": [METRIC_NAME]}],
        "customMetricConfig": {
            "customMetrics": [custom_metric(judge_prompt)],
            "evaluatorModelConfig": evaluator(config.judge_model_id),
        },
        "evaluatorModelConfig": evaluator(config.judge_model_id),
    }


def job_request(config: JobConfig, judge_prompt: str) -> dict[str, Any]:
    return {
        "jobName": config.job_name,
        "roleArn": config.role_arn,
        "applicationType": "ModelEvaluation",
        "evaluationConfig": {"automated": automated_config(config, judge_prompt)},
        "inferenceConfig": {
            "models": [{"precomputedInferenceSource": {"inferenceSourceIdentifier": MODEL_IDENTIFIER}}]
        },
        "outputDataConfig": {"s3Uri": config.output_uri()},
    }


def submit(config: JobConfig, dataset: Path, s3: S3Client, client: EvaluationClient) -> str:
    """Upload the dataset, start the job and return its ARN."""
    log.info("upload %s to %s", dataset, config.dataset_uri())
    s3.upload_file(Filename=str(dataset), Bucket=config.bucket, Key=config.dataset_key())
    request = job_request(config, load_prompt("judge"))
    log.info("request %s", json.dumps(request))
    response = client.create_evaluation_job(**request)
    log.info("response %s", json.dumps(response))
    return response["jobArn"]


def config_from_env() -> JobConfig:
    return JobConfig(
        role_arn=os.environ.get("BEDROCK_EVAL_ROLE_ARN", PLACEHOLDER_ROLE),
        bucket=os.environ.get("BEDROCK_EVAL_BUCKET", PLACEHOLDER_BUCKET),
        prefix=os.environ.get("BEDROCK_EVAL_PREFIX", "eval-harness"),
        judge_model_id=os.environ.get(
            "BEDROCK_EVAL_JUDGE_MODEL_ID", "us.anthropic.claude-opus-4-5-20251101-v1:0"
        ),
        region=os.environ.get("AWS_REGION", "us-east-1"),
        job_name=f"eval-harness-v2-{time.strftime('%Y%m%d-%H%M%S').lower()}",
    )


def require_real_values(config: JobConfig) -> None:
    if config.role_arn == PLACEHOLDER_ROLE or config.bucket == PLACEHOLDER_BUCKET:
        raise SystemExit("set BEDROCK_EVAL_ROLE_ARN and BEDROCK_EVAL_BUCKET before --submit")


def make_clients(region: str) -> tuple[S3Client, EvaluationClient]:
    import boto3

    return boto3.client("s3", region_name=region), boto3.client("bedrock", region_name=region)


def print_dry_run(config: JobConfig, dataset: Path) -> None:
    print(f"dataset written: {dataset} ({len(dataset.read_text().splitlines())} rows)")
    print("create_evaluation_job request (dry run, nothing sent):")
    print(json.dumps(job_request(config, load_prompt("judge")), indent=2))


def print_submitted(config: JobConfig, arn: str) -> None:
    print(f"job started: {arn}")
    print(f"status: aws bedrock get-evaluation-job --job-identifier {arn} --region {config.region}")
    print(f"results land under {config.output_uri()}{config.job_name}/")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="default: print the request, send nothing")
    mode.add_argument("--submit", action="store_true", help="upload and start the job (costs money)")
    args = p.parse_args()
    config = config_from_env()
    dataset = write_dataset()
    if not args.submit:
        print_dry_run(config, dataset)
        return
    require_real_values(config)
    logging.basicConfig(filename=LAB_ROOT / "live.log", level=logging.INFO)
    s3, client = make_clients(config.region)
    print_submitted(config, submit(config, dataset, s3, client))


if __name__ == "__main__":
    main()
