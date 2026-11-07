"""Live mode: call a model on Amazon Bedrock through the Converse API.

toolChoice forces the model to answer by calling a tool whose input schema is the Triage enum.
Forcing the tool does not guarantee the input matches the schema, so graders.parse_triage still
validates every answer. Some newer models reject a forced toolChoice; check the model's docs
before overriding TRIAGE_MODEL_ID or JUDGE_MODEL_ID.

The triage call keeps the model's default sampling, so reruns vary (step B3). The judge runs at
temperature 0 to keep its verdicts as stable as possible; even that is not fully deterministic.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol

TRIAGE_MODEL_ID = os.environ.get("TRIAGE_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
JUDGE_MODEL_ID = os.environ.get("JUDGE_MODEL_ID", "global.anthropic.claude-opus-4-5-20251101-v1:0")
MAX_TOKENS = 400
DEFAULT_REGION = "us-east-1"

log = logging.getLogger("harness.live")

TRIAGE_TOOL = {
    "toolSpec": {
        "name": "record_triage",
        "description": "Record the priority of one insurance claim and a one-sentence reason.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "priority": {"type": "string", "enum": ["urgent", "standard", "fast_track"]},
                    "reason": {"type": "string"},
                },
                "required": ["priority", "reason"],
            }
        },
    }
}


class ConverseClient(Protocol):
    def converse(self, **kwargs: Any) -> dict[str, Any]: ...


def region() -> str:
    """AWS_REGION, else AWS_DEFAULT_REGION, else us-east-1 (where the default inference profiles run)."""
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or DEFAULT_REGION


def make_client() -> ConverseClient:
    """bedrock-runtime client: up to 8 attempts in adaptive mode (backoff with jitter on throttling)."""
    import boto3
    from botocore.config import Config

    config = Config(retries={"total_max_attempts": 8, "mode": "adaptive"})
    return boto3.client("bedrock-runtime", region_name=region(), config=config)


def triage_request(system: str, claim: str, structured: bool) -> dict[str, Any]:
    request: dict[str, Any] = {
        "modelId": TRIAGE_MODEL_ID,
        "system": [{"text": system}],
        "messages": [{"role": "user", "content": [{"text": claim}]}],
        "inferenceConfig": {"maxTokens": MAX_TOKENS},
    }
    if structured:
        request["toolConfig"] = {
            "tools": [TRIAGE_TOOL],
            "toolChoice": {"tool": {"name": "record_triage"}},
        }
    return request


def output_text(response: dict[str, Any]) -> str:
    """The tool input as a JSON string when the model called the tool, else its text."""
    for block in response["output"]["message"]["content"]:
        if "toolUse" in block:
            return json.dumps(block["toolUse"]["input"])
    return "".join(block.get("text", "") for block in response["output"]["message"]["content"])


def call(client: ConverseClient, request: dict[str, Any]) -> str:
    log.info("request %s", json.dumps(request))
    response = client.converse(**request)
    text = output_text(response)
    log.info("response %s", text)
    return text


VERDICT_TOOL = {
    "toolSpec": {
        "name": "record_verdict",
        "description": "Record whether the triage reason respects the urgent rules.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "verdict": {"type": "string", "enum": ["pass", "fail"]},
                    "rule_violated": {"type": ["string", "null"]},
                },
                "required": ["verdict", "rule_violated"],
            }
        },
    }
}


def judge_request(system: str, claim: str, priority: str, reason: str) -> dict[str, Any]:
    text = f"Claim: {claim}\nPriority chosen: {priority}\nReason given: {reason}"
    return {
        "modelId": JUDGE_MODEL_ID,
        "system": [{"text": system}],
        "messages": [{"role": "user", "content": [{"text": text}]}],
        "inferenceConfig": {"maxTokens": MAX_TOKENS, "temperature": 0},
        "toolConfig": {"tools": [VERDICT_TOOL], "toolChoice": {"tool": {"name": "record_verdict"}}},
    }
