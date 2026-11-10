"""Read an InvokeHarness event stream into one result (walkthrough step A1).

The harness always replies with a stream. One stream can hold several messages: the assistant asking for a
tool, the harness running it and returning the result, and the assistant answering. A tool the harness runs
itself (Gateway, MCP) shows up with its result in the stream. An inline function has no result yet: the
stream stops with stopReason "tool_use" and your app must answer it.
"""

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from botocore.exceptions import EventStreamError

RETRYABLE_EVENTS = {"internalServerException"}
ERROR_EVENTS = {"internalServerException", "validationException", "runtimeClientError"}


class StreamError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.retryable = kind in RETRYABLE_EVENTS


@dataclass
class ToolCall:
    tool_use_id: str
    name: str
    input: dict


@dataclass
class TurnResult:
    text: str = ""
    stop_reason: str | None = None
    pending: list[ToolCall] = field(default_factory=list)
    tools_run: list[str] = field(default_factory=list)
    usage: dict | None = None


@dataclass
class _Block:
    tool_use_id: str | None = None
    name: str | None = None
    input_json: str = ""
    text: str = ""


def read_stream(events: Iterable[dict]) -> TurnResult:
    result = TurnResult()
    calls: dict[str, ToolCall] = {}
    answered: set[str] = set()
    blocks: dict[int, _Block] = {}
    message_text = ""
    for event in _events(events):
        kind, body = next(iter(event.items()))
        if kind in ERROR_EVENTS:
            raise StreamError(kind, body.get("message", ""))
        if kind == "messageStart":
            blocks, message_text = {}, ""
        elif kind == "contentBlockStart":
            blocks[body["contentBlockIndex"]] = _start_block(body["start"], answered)
        elif kind == "contentBlockDelta":
            _add_delta(blocks.setdefault(body["contentBlockIndex"], _Block()), body["delta"])
        elif kind == "contentBlockStop":
            block = blocks.get(body["contentBlockIndex"], _Block())
            message_text += block.text
            if block.tool_use_id:
                calls[block.tool_use_id] = ToolCall(
                    block.tool_use_id, block.name or "", _parse(block.input_json)
                )
        elif kind == "messageStop":
            result.stop_reason = body.get("stopReason")
            if message_text:
                result.text = message_text
        elif kind == "metadata":
            result.usage = body.get("usage")
    result.tools_run = [c.name for i, c in calls.items() if i in answered]
    if result.stop_reason == "tool_use":
        result.pending = [c for i, c in calls.items() if i not in answered]
    return result


def _events(events: Iterable[dict]) -> Iterator[dict]:
    """boto3 raises in-stream errors while you iterate; turn them back into error events."""
    try:
        yield from events
    except EventStreamError as err:
        error = err.response.get("Error", {})
        yield {error.get("Code", "runtimeClientError"): {"message": error.get("Message", "")}}


def _start_block(start: dict, answered: set[str]) -> _Block:
    if "toolUse" in start:
        return _Block(tool_use_id=start["toolUse"]["toolUseId"], name=start["toolUse"]["name"])
    if "toolResult" in start:
        answered.add(start["toolResult"]["toolUseId"])
    return _Block()


def _add_delta(block: _Block, delta: dict) -> None:
    if "text" in delta:
        block.text += delta["text"]
    elif "toolUse" in delta:
        block.input_json += delta["toolUse"].get("input", "")


def _parse(input_json: str) -> dict:
    return json.loads(input_json) if input_json.strip() else {}
