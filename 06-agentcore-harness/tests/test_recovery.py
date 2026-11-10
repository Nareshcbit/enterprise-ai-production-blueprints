"""After a crash the harness waits for the pending toolUseId; the app must remember it (steps D1, D2)."""

import pytest

from harnesskit.agent import SimulatedCrash, Target, run
from harnesskit.payments import InMemoryPayments
from harnesskit.pending import PendingStore
from tests.fakes import ScriptedHarness, refund_pending, text_message

TARGET = Target(harness_arn="arn:aws:bedrock-agentcore:us-east-1:111122223333:harness/refund-AbCdEfGhIj")
SESSION = "s" * 40


def go(client, payments, store, **kw):
    return run(
        client,
        TARGET,
        session_id=SESSION,
        actor_id="customer-3001",
        prompt="Refund A-1042.",
        approve=lambda c: True,
        payments=payments,
        pending=store,
        backoff_seconds=0,
        **kw,
    )


def test_pending_call_is_saved_before_paying(tmp_path):
    store = PendingStore(tmp_path)
    with pytest.raises(SimulatedCrash):
        go(ScriptedHarness([refund_pending()]), InMemoryPayments(), store, crash_after_pay=True)
    saved = store.load(SESSION)
    assert saved is not None and saved.tool_use_id == "tu-1" and saved.input["charge_id"] == "ch_88"


def test_restart_answers_the_pending_call_instead_of_sending_a_new_message(tmp_path):
    store, payments = PendingStore(tmp_path), InMemoryPayments()
    with pytest.raises(SimulatedCrash):
        go(ScriptedHarness([refund_pending()]), payments, store, crash_after_pay=True)
    client = ScriptedHarness([text_message("Refunded.")])
    result = go(client, payments, store)
    first = client.calls[0]["messages"][0]["content"][0]
    assert first["toolResult"]["toolUseId"] == "tu-1"
    assert '"duplicate": true' in first["toolResult"]["content"][0]["text"]
    assert payments.total_refunded_cents() == 4250
    assert result.text == "Refunded."
    assert store.load(SESSION) is None
