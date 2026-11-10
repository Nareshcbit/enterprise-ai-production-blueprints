"""A fake payment system that honors an idempotency key (walkthrough steps D1 and D2).

No real money moves. The refund ID is built from the order and the charge, so a repeat of the same refund,
after a crash or a retry, returns the first refund instead of paying again.
"""

from botocore.exceptions import ClientError


def refund_id(order_id: str, charge_id: str) -> str:
    return f"{order_id}:{charge_id}"


class InMemoryPayments:
    def __init__(self) -> None:
        self._refunds: dict[str, dict] = {}

    def refund(self, order_id: str, charge_id: str, amount_cents: int) -> dict:
        key = refund_id(order_id, charge_id)
        if key in self._refunds:
            return {**self._refunds[key], "duplicate": True}
        self._refunds[key] = {"refund_id": key, "amount_cents": amount_cents}
        return {**self._refunds[key], "duplicate": False}

    def total_refunded_cents(self) -> int:
        return sum(r["amount_cents"] for r in self._refunds.values())


class DynamoPayments:
    """Refunds stored in a DynamoDB table whose partition key is refund_id."""

    def __init__(self, dynamodb_client, table_name: str) -> None:
        self._db = dynamodb_client
        self._table = table_name

    def refund(self, order_id: str, charge_id: str, amount_cents: int) -> dict:
        key = refund_id(order_id, charge_id)
        item = {"refund_id": {"S": key}, "amount_cents": {"N": str(amount_cents)}}
        try:
            self._db.put_item(
                TableName=self._table, Item=item, ConditionExpression="attribute_not_exists(refund_id)"
            )
        except ClientError as err:
            if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            return {**self._read(key), "duplicate": True}
        return {"refund_id": key, "amount_cents": amount_cents, "duplicate": False}

    def _read(self, key: str) -> dict:
        item = self._db.get_item(TableName=self._table, Key={"refund_id": {"S": key}})["Item"]
        return {"refund_id": key, "amount_cents": int(item["amount_cents"]["N"])}
