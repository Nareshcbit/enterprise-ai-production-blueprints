"""The client: actorId on every call, approval before paying, safe retries (steps A1, B2, B4, D1, D2)."""

import pytest

from harnesskit.agent import SimulatedCrash, Target, make_session_id, run
from harnesskit.payments import InMemoryPayments
from harnesskit.stream import StreamError
from tests.fakes import ScriptedHarness, refund_pending, retryable_error, text_message

TARGET = Target(
    harness_arn="arn:aws:bedrock-agentcore:us-east-1:111122223333:harness/refund-AbCdEfGhIj", qualifier="prod"
)


def approve_all(call):
    return True


def run_once(client, payments, approve=approve_all, **kw):
    return run(
        client,
        TARGET,
        session_id="s" * 40,
        actor_id="customer-1042",
        prompt="Refund the duplicate charge on order A-1042.",
        approve=approve,
        payments=payments,
        backoff_seconds=0,
        **kw,
    )


def test_every_call_names_the_customer_endpoint_and_session():
    client = ScriptedHarness([refund_pending(), text_message("Refunded $42.50.")])
    run_once(client, InMemoryPayments())
    for call in client.calls:
        assert call["actorId"] == "customer-1042"
        assert call["qualifier"] == "prod"
        assert call["runtimeSessionId"] == "s" * 40
        assert call["harnessArn"] == TARGET.harness_arn


PAID = '{"refund_id": "A-1042:ch_88", "amount_cents": 4250, "duplicate": false}'


def test_approved_refund_is_paid_once_and_answered():
    client = ScriptedHarness([refund_pending(), text_message("Refunded $42.50.")])
    payments = InMemoryPayments()
    result = run_once(client, payments)
    assert result.text == "Refunded $42.50."
    assert payments.total_refunded_cents() == 4250
    answer = client.calls[1]["messages"]
    assert answer == [
        {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": "tu-1",
                        "status": "success",
                        "content": [{"text": PAID}],
                    }
                }
            ],
        }
    ]


def test_denied_refund_is_not_paid():
    client = ScriptedHarness([refund_pending(), text_message("I can't refund without approval.")])
    payments = InMemoryPayments()
    run_once(client, payments, approve=lambda call: False)
    assert payments.total_refunded_cents() == 0
    result_block = client.calls[1]["messages"][0]["content"][0]["toolResult"]
    assert result_block["status"] == "error"


def test_retryable_stream_error_is_retried():
    client = ScriptedHarness([retryable_error(), text_message("Done.")])
    assert run_once(client, InMemoryPayments()).text == "Done."
    assert len(client.calls) == 2


def test_non_retryable_error_is_raised():
    client = ScriptedHarness([[{"runtimeClientError": {"message": "bad"}}]])
    with pytest.raises(StreamError):
        run_once(client, InMemoryPayments())


def test_retries_stop_after_the_limit():
    client = ScriptedHarness([retryable_error(), retryable_error(), retryable_error()])
    with pytest.raises(StreamError):
        run_once(client, InMemoryPayments(), max_attempts=3)
    assert len(client.calls) == 3


def test_crash_after_paying_then_rerun_pays_once():
    payments = InMemoryPayments()
    with pytest.raises(SimulatedCrash):
        run_once(ScriptedHarness([refund_pending()]), payments, crash_after_pay=True)
    run_once(ScriptedHarness([refund_pending(), text_message("Refunded.")]), payments)
    assert payments.total_refunded_cents() == 4250


def test_unknown_inline_tool_is_refused_not_run():
    from tests.fakes import tool_call

    pending = tool_call("tu-2", "delete_account", "{}") + [{"messageStop": {"stopReason": "tool_use"}}]
    client = ScriptedHarness([pending, text_message("ok")])
    run_once(client, InMemoryPayments())
    assert client.calls[1]["messages"][0]["content"][0]["toolResult"]["status"] == "error"


def test_session_id_fits_the_33_to_100_character_rule():
    sid = make_session_id("customer-1042", "A-1042")
    assert 33 <= len(sid) <= 100
    assert make_session_id("customer-1042", "A-1042") != sid


def test_tools_run_are_collected_across_rounds():
    from tests.fakes import tool_call, tool_result

    first = (
        tool_call("tu-9", "charges___lookup_charges", '{"order_id": "A-1042"}', kind="mcp_tool_use")
        + tool_result("tu-9")
        + refund_pending()
    )
    client = ScriptedHarness([first, text_message("Refunded.")])
    result = run_once(client, InMemoryPayments())
    assert result.tools_run == ["charges___lookup_charges", "refund"]
