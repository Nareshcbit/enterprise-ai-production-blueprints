"""Run one refund conversation against the harness (walkthrough steps A1, B2, B4, D1, D2).

- Every call names the customer (actorId) so memory stays per customer, and a named endpoint (qualifier)
  so a new harness version doesn't reach production until you move the endpoint.
- The refund is an inline function: the harness stops, a person approves, your app pays with an
  idempotency key, then answers with a toolResult on the same session.
- Only errors AWS documents as retryable are retried, with backoff.
"""

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from botocore.exceptions import ClientError

from harnesskit.payments import InMemoryPayments
from harnesskit.pending import PendingStore
from harnesskit.stream import StreamError, ToolCall, TurnResult, read_stream

RETRYABLE_CODES = {"ThrottlingException", "InternalServerException"}
INLINE_TOOLS = {"refund"}


class SimulatedCrash(Exception):
    """Raised by --crash-after-pay to show what a crash between paying and answering does."""


@dataclass
class Target:
    harness_arn: str
    qualifier: str | None = None


def make_session_id(actor_id: str, order_id: str) -> str:
    return f"refund-{actor_id}-{order_id}-{uuid.uuid4().hex}"[:100]


def run(
    client,
    target: Target,
    session_id: str,
    actor_id: str,
    prompt: str,
    approve: Callable[[ToolCall], bool],
    payments: InMemoryPayments,
    crash_after_pay: bool = False,
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
    max_rounds: int = 5,
    pending: PendingStore | None = None,
) -> TurnResult:
    saved = pending.load(session_id) if pending else None
    if saved:  # restarted after a crash: the harness only accepts the answer to this call
        messages = [{"role": "user", "content": [_answer(saved, approve, payments, False)]}]
    else:
        messages = [{"role": "user", "content": [{"text": prompt}]}]
    tools_run: list[str] = []
    for _ in range(max_rounds):
        result = _invoke(client, target, session_id, actor_id, messages, max_attempts, backoff_seconds)
        if pending:
            pending.clear(session_id)  # the harness accepted what we sent
        tools_run += result.tools_run
        if result.stop_reason != "tool_use" or not result.pending:
            result.tools_run = tools_run
            return result
        tools_run += [call.name for call in result.pending]
        blocks = []
        for call in result.pending:
            if pending:
                pending.save(session_id, call)  # before paying, so a restart can answer it
            blocks.append(_answer(call, approve, payments, crash_after_pay))
        messages = [{"role": "user", "content": blocks}]
    raise RuntimeError(f"no final answer after {max_rounds} rounds")


def _invoke(client, target, session_id, actor_id, messages, max_attempts, backoff_seconds) -> TurnResult:
    request = {
        "harnessArn": target.harness_arn,
        "runtimeSessionId": session_id,
        "actorId": actor_id,
        "messages": messages,
    }
    if target.qualifier:
        request["qualifier"] = target.qualifier
    for attempt in range(1, max_attempts + 1):
        try:
            return read_stream(client.invoke_harness(**request)["stream"])
        except StreamError as err:
            if not err.retryable or attempt == max_attempts:
                raise
        except ClientError as err:
            if err.response["Error"]["Code"] not in RETRYABLE_CODES or attempt == max_attempts:
                raise
        time.sleep(backoff_seconds * 2 ** (attempt - 1))
    raise AssertionError("unreachable")


def _answer(call: ToolCall, approve, payments, crash_after_pay: bool) -> dict:
    if call.name not in INLINE_TOOLS:
        return _result(call, "error", {"error": f"{call.name} is not available"})
    if not approve(call):
        return _result(call, "error", {"error": "Refund not approved by a person"})
    paid = payments.refund(call.input["order_id"], call.input["charge_id"], int(call.input["amount_cents"]))
    if crash_after_pay:
        raise SimulatedCrash(f"crashed after paying {paid['refund_id']}, before answering the harness")
    return _result(call, "success", paid)


def _result(call: ToolCall, status: str, body: dict) -> dict:
    # The harness accepts text tool results; a json content block fails with "unsupported type".
    content = [{"text": json.dumps(body)}]
    return {"toolResult": {"toolUseId": call.tool_use_id, "status": status, "content": content}}
