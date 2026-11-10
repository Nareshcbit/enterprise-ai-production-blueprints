"""Reading the InvokeHarness event stream (walkthrough step A1)."""

import pytest

from harnesskit.stream import StreamError, read_stream
from tests.fakes import REFUND_INPUT, refund_pending, text_message, tool_call, tool_result


def test_text_reply():
    result = read_stream(text_message("Refund sent."))
    assert result.text == "Refund sent."
    assert result.stop_reason == "end_turn"
    assert result.pending == []


def test_inline_function_is_pending_with_parsed_input():
    result = read_stream(refund_pending())
    assert result.stop_reason == "tool_use"
    assert len(result.pending) == 1
    call = result.pending[0]
    assert (call.tool_use_id, call.name) == ("tu-1", "refund")
    assert call.input == {"order_id": "A-1042", "charge_id": "ch_88", "amount_cents": 4250}


def test_tool_the_harness_already_ran_is_not_pending():
    events = (
        tool_call("tu-9", "charges___lookup_charges", '{"order_id": "A-1042"}', kind="mcp_tool_use")
        + tool_result("tu-9")
        + text_message("Two charges found.")
    )
    result = read_stream(events)
    assert result.pending == []
    assert result.tools_run == ["charges___lookup_charges"]


def test_final_text_is_the_last_message():
    result = read_stream(text_message("Looking...", stop="tool_result") + text_message("Done."))
    assert result.text == "Done."


def test_internal_error_in_stream_is_retryable():
    with pytest.raises(StreamError) as err:
        read_stream([{"internalServerException": {"message": "boom"}}])
    assert err.value.retryable


def test_client_error_in_stream_is_not_retryable():
    with pytest.raises(StreamError) as err:
        read_stream([{"runtimeClientError": {"message": "bad tool"}}])
    assert not err.value.retryable


def test_token_usage_is_kept():
    events = text_message("ok") + [
        {"metadata": {"usage": {"inputTokens": 10, "outputTokens": 3}, "metrics": {}}}
    ]
    assert read_stream(events).usage == {"inputTokens": 10, "outputTokens": 3}


def test_refund_input_fixture_is_valid_json():
    import json

    assert json.loads(REFUND_INPUT)["amount_cents"] == 4250


def _raising_stream(code: str):
    from botocore.exceptions import EventStreamError

    yield {"messageStart": {"role": "assistant"}}
    raise EventStreamError({"Error": {"Code": code, "Message": "from boto3"}}, "InvokeHarness")


def test_boto3_raises_stream_errors_mid_iteration_and_they_are_mapped():
    with pytest.raises(StreamError) as err:
        read_stream(_raising_stream("internalServerException"))
    assert err.value.retryable
    with pytest.raises(StreamError) as err:
        read_stream(_raising_stream("runtimeClientError"))
    assert not err.value.retryable
