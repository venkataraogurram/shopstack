"""Order persistence: in-memory for local/test, DynamoDB in production.

Order creation uses a conditional write so a retried request with the same
order id can never overwrite an existing order.
"""

import os
from typing import Protocol


class OrderStore(Protocol):
    def create(self, order: dict) -> None: ...
    def get(self, order_id: str) -> dict | None: ...
    def ping(self) -> None: ...


class DuplicateOrder(Exception):
    pass


class MemoryOrderStore:
    def __init__(self) -> None:
        self._orders: dict[str, dict] = {}

    def create(self, order: dict) -> None:
        if order["order_id"] in self._orders:
            raise DuplicateOrder(order["order_id"])
        self._orders[order["order_id"]] = order

    def get(self, order_id: str) -> dict | None:
        return self._orders.get(order_id)

    def ping(self) -> None:
        return None


class DynamoOrderStore:
    def __init__(self, table_name: str, region: str | None = None) -> None:
        import boto3

        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        self._client = self._table.meta.client
        self._table_name = table_name

    def create(self, order: dict) -> None:
        from botocore.exceptions import ClientError

        try:
            self._table.put_item(Item=order, ConditionExpression="attribute_not_exists(order_id)")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise DuplicateOrder(order["order_id"]) from e
            raise

    def get(self, order_id: str) -> dict | None:
        item = self._table.get_item(Key={"order_id": order_id}, ConsistentRead=True).get("Item")
        if item is None:
            return None
        item["total_cents"] = int(item["total_cents"])
        item["created_at"] = int(item["created_at"])
        for line in item["items"]:
            line["unit_price_cents"] = int(line["unit_price_cents"])
            line["qty"] = int(line["qty"])
            line["line_total_cents"] = int(line["line_total_cents"])
        return item

    def ping(self) -> None:
        self._client.describe_table(TableName=self._table_name)


def build_store() -> OrderStore:
    backend = os.environ.get("STORE_BACKEND", "memory").lower()
    if backend == "dynamodb":
        return DynamoOrderStore(os.environ["ORDER_TABLE"], os.environ.get("AWS_REGION"))
    if backend == "memory":
        return MemoryOrderStore()
    raise ValueError(f"unsupported STORE_BACKEND={backend!r}")
