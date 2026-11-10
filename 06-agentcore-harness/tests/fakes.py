"""Test doubles: a scripted harness client and helpers that build stream events."""

from harnesskit.stream import StreamError


def text_message(text: str, stop: str = "end_turn") -> list[dict]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"contentBlockIndex": 0, "start": {}}},
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": text}}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"messageStop": {"stopReason": stop}},
    ]


def tool_call(tool_use_id: str, name: str, input_json: str, kind: str = "tool_use") -> list[dict]:
    half = len(input_json) // 2
    return [
        {"messageStart": {"role": "assistant"}},
        {
            "contentBlockStart": {
                "contentBlockIndex": 0,
                "start": {"toolUse": {"toolUseId": tool_use_id, "name": name, "type": kind}},
            }
        },
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": input_json[:half]}}}},
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": input_json[half:]}}}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
    ]


def tool_result(tool_use_id: str) -> list[dict]:
    return [
        {"messageStart": {"role": "user"}},
        {"contentBlockStart": {"contentBlockIndex": 0, "start": {"toolResult": {"toolUseId": tool_use_id}}}},
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolResult": [{"text": "ok"}]}}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
    ]


REFUND_INPUT = '{"order_id": "A-1042", "charge_id": "ch_88", "amount_cents": 4250}'


def refund_pending() -> list[dict]:
    return tool_call("tu-1", "refund", REFUND_INPUT) + [{"messageStop": {"stopReason": "tool_use"}}]


class ScriptedHarness:
    """Stands in for the bedrock-agentcore client. Each script item is a list of events or an exception."""

    def __init__(self, script: list):
        self.script = list(script)
        self.calls: list[dict] = []

    def invoke_harness(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return {"stream": iter(item)}


def retryable_error() -> list[dict]:
    return [{"internalServerException": {"message": "try again"}}]


__all__ = [
    "StreamError",
    "ScriptedHarness",
    "text_message",
    "tool_call",
    "tool_result",
    "refund_pending",
    "retryable_error",
    "REFUND_INPUT",
]
