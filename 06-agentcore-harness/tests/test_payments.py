"""The fake payment system honors an idempotency key (walkthrough steps D1 and D2)."""

from botocore.exceptions import ClientError

from harnesskit.payments import DynamoPayments, InMemoryPayments, refund_id


def test_refund_id_comes_from_order_and_charge():
    assert refund_id("A-1042", "ch_88") == "A-1042:ch_88"


def test_same_refund_twice_pays_once():
    payments = InMemoryPayments()
    first = payments.refund("A-1042", "ch_88", 4250)
    second = payments.refund("A-1042", "ch_88", 4250)
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["refund_id"] == first["refund_id"]
    assert payments.total_refunded_cents() == 4250


class FakeTable:
    """Mimics the boto3 DynamoDB client calls DynamoPayments uses."""

    def __init__(self):
        self.items: dict[str, dict] = {}
        self.puts: list[dict] = []

    def put_item(self, **kwargs):
        self.puts.append(kwargs)
        key = kwargs["Item"]["refund_id"]["S"]
        if key in self.items:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}}, "PutItem"
            )
        self.items[key] = kwargs["Item"]

    def get_item(self, **kwargs):
        return {"Item": self.items[kwargs["Key"]["refund_id"]["S"]]}


def test_dynamo_write_is_conditional_on_the_refund_id():
    table = FakeTable()
    payments = DynamoPayments(table, "payments")
    payments.refund("A-1042", "ch_88", 4250)
    assert table.puts[0]["ConditionExpression"] == "attribute_not_exists(refund_id)"


def test_dynamo_repeat_returns_the_first_refund():
    table = FakeTable()
    payments = DynamoPayments(table, "payments")
    first = payments.refund("A-1042", "ch_88", 4250)
    second = payments.refund("A-1042", "ch_88", 4250)
    assert second["duplicate"] is True
    assert second["refund_id"] == first["refund_id"]
    assert len(table.items) == 1
