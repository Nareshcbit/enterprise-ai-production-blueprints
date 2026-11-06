"""Live mode request shape, checked with a stub client (no AWS call)."""

import json
from typing import Any

from harness import bedrock


class StubClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.request: dict[str, Any] = {}

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.request = kwargs
        return self.response


def tool_response(payload: dict[str, Any]) -> dict[str, Any]:
    block = {"toolUse": {"toolUseId": "t1", "name": "record_triage", "input": payload}}
    return {"output": {"message": {"role": "assistant", "content": [block]}}}


def test_structured_request_forces_the_triage_tool() -> None:
    req = bedrock.triage_request("sys", "claim", structured=True)
    assert req["toolConfig"]["toolChoice"] == {"tool": {"name": "record_triage"}}
    assert req["inferenceConfig"]["maxTokens"] == bedrock.MAX_TOKENS


def test_call_returns_tool_input_as_json() -> None:
    client = StubClient(tool_response({"priority": "urgent", "reason": "x"}))
    out = bedrock.call(client, bedrock.triage_request("sys", "claim", structured=True))
    assert json.loads(out) == {"priority": "urgent", "reason": "x"}
    assert client.request["modelId"] == bedrock.TRIAGE_MODEL_ID
