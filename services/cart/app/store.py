"""Cart persistence with two interchangeable backends.

- MemoryCartStore: local development and unit tests.
- DynamoCartStore: production. Credentials come from the pod's IAM role
  (EKS Pod Identity); no keys are configured in the application.

Prices are stored as integer cents so DynamoDB never sees floats.
"""

import os
import time
from typing import Protocol

Item = dict  # {"sku", "name", "unit_price_cents", "qty"}


class CartStore(Protocol):
    def get(self, cart_id: str) -> dict | None: ...
    def put_item(self, cart_id: str, item: Item) -> dict: ...
    def remove_item(self, cart_id: str, sku: str) -> dict | None: ...
    def delete(self, cart_id: str) -> None: ...
    def ping(self) -> None: ...


def _empty(cart_id: str) -> dict:
    return {"cart_id": cart_id, "items": {}, "updated_at": int(time.time())}


class MemoryCartStore:
    def __init__(self) -> None:
        self._carts: dict[str, dict] = {}

    def get(self, cart_id: str) -> dict | None:
        return self._carts.get(cart_id)

    def put_item(self, cart_id: str, item: Item) -> dict:
        cart = self._carts.setdefault(cart_id, _empty(cart_id))
        cart["items"][item["sku"]] = item
        cart["updated_at"] = int(time.time())
        return cart

    def remove_item(self, cart_id: str, sku: str) -> dict | None:
        cart = self._carts.get(cart_id)
        if cart is None:
            return None
        cart["items"].pop(sku, None)
        cart["updated_at"] = int(time.time())
        return cart

    def delete(self, cart_id: str) -> None:
        self._carts.pop(cart_id, None)

    def ping(self) -> None:
        return None


class DynamoCartStore:
    def __init__(self, table_name: str, region: str | None = None) -> None:
        import boto3  # imported lazily so the memory backend needs no AWS SDK

        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        self._client = self._table.meta.client
        self._table_name = table_name

    @staticmethod
    def _to_native(cart: dict | None) -> dict | None:
        # DynamoDB returns numbers as Decimal; the API contract is int cents.
        if cart is None:
            return None
        for item in cart.get("items", {}).values():
            item["unit_price_cents"] = int(item["unit_price_cents"])
            item["qty"] = int(item["qty"])
        cart["updated_at"] = int(cart.get("updated_at", 0))
        return cart

    def get(self, cart_id: str) -> dict | None:
        resp = self._table.get_item(Key={"cart_id": cart_id}, ConsistentRead=True)
        return self._to_native(resp.get("Item"))

    def put_item(self, cart_id: str, item: Item) -> dict:
        now = int(time.time())
        # Two atomic updates: make sure the items map exists, then set the
        # single SKU entry. Concurrent writers to different SKUs never clobber
        # each other, which a read-modify-write of the whole cart would.
        self._table.update_item(
            Key={"cart_id": cart_id},
            UpdateExpression="SET #items = if_not_exists(#items, :empty), updated_at = :now",
            ExpressionAttributeNames={"#items": "items"},
            ExpressionAttributeValues={":empty": {}, ":now": now},
        )
        resp = self._table.update_item(
            Key={"cart_id": cart_id},
            UpdateExpression="SET #items.#sku = :item, updated_at = :now",
            ExpressionAttributeNames={"#items": "items", "#sku": item["sku"]},
            ExpressionAttributeValues={":item": item, ":now": now},
            ReturnValues="ALL_NEW",
        )
        return self._to_native(resp["Attributes"])

    def remove_item(self, cart_id: str, sku: str) -> dict | None:
        from botocore.exceptions import ClientError

        try:
            resp = self._table.update_item(
                Key={"cart_id": cart_id},
                UpdateExpression="REMOVE #items.#sku SET updated_at = :now",
                ConditionExpression="attribute_exists(cart_id)",
                ExpressionAttributeNames={"#items": "items", "#sku": sku},
                ExpressionAttributeValues={":now": int(time.time())},
                ReturnValues="ALL_NEW",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise
        return self._to_native(resp["Attributes"])

    def delete(self, cart_id: str) -> None:
        self._table.delete_item(Key={"cart_id": cart_id})

    def ping(self) -> None:
        self._client.describe_table(TableName=self._table_name)


def build_store() -> CartStore:
    backend = os.environ.get("STORE_BACKEND", "memory").lower()
    if backend == "dynamodb":
        return DynamoCartStore(os.environ["CART_TABLE"], os.environ.get("AWS_REGION"))
    if backend == "memory":
        return MemoryCartStore()
    raise ValueError(f"unsupported STORE_BACKEND={backend!r}")
