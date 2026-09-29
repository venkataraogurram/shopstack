"""Order service: turns a cart into an immutable order.

Checkout flow:
  1. fetch the cart from the cart service,
  2. re-check every SKU against the catalog (price and stock may have changed),
  3. persist the order with a conditional write,
  4. clear the cart (best effort; the order is already durable).
"""

import os
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .observability import REQUEST_ID_HEADER, configure_logging, current_request_id, install_request_logging
from .store import DuplicateOrder, OrderStore, build_store

SERVICE = "order"
CART_URL = os.environ.get("CART_URL", "http://localhost:8082").rstrip("/")
CATALOG_URL = os.environ.get("CATALOG_URL", "http://localhost:8081").rstrip("/")
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "2.0"))

log = configure_logging(SERVICE, os.environ.get("LOG_LEVEL", "INFO"))
store: OrderStore
cart_client: httpx.AsyncClient
catalog_client: httpx.AsyncClient


@asynccontextmanager
async def lifespan(_: FastAPI):
    global store, cart_client, catalog_client
    store = build_store()
    cart_client = httpx.AsyncClient(base_url=CART_URL, timeout=HTTP_TIMEOUT)
    catalog_client = httpx.AsyncClient(base_url=CATALOG_URL, timeout=HTTP_TIMEOUT)
    log.info(
        "order started",
        extra={"extra_fields": {"backend": type(store).__name__, "cart_url": CART_URL, "catalog_url": CATALOG_URL}},
    )
    yield
    await cart_client.aclose()
    await catalog_client.aclose()


app = FastAPI(title="ShopStack Order", version=os.environ.get("APP_VERSION", "dev"), lifespan=lifespan)
install_request_logging(app, log)


class Checkout(BaseModel):
    cart_id: str = Field(min_length=1, max_length=64)
    customer_email: str = Field(min_length=3, max_length=254)


class OrderLine(BaseModel):
    sku: str
    name: str
    unit_price_cents: int
    qty: int
    line_total_cents: int


class Order(BaseModel):
    order_id: str
    cart_id: str
    customer_email: str
    items: list[OrderLine]
    total_cents: int
    currency: str
    status: str
    created_at: int


def _headers() -> dict:
    return {REQUEST_ID_HEADER: current_request_id()}


async def _call(client: httpx.AsyncClient, name: str, method: str, path: str) -> httpx.Response:
    try:
        return await client.request(method, path, headers=_headers())
    except httpx.HTTPError as e:
        log.warning(f"{name} unreachable", extra={"extra_fields": {"error": str(e)}})
        raise HTTPException(status_code=503, detail=f"{name} service unavailable") from e


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok", "service": SERVICE}


@app.get("/ready", include_in_schema=False)
def ready():
    try:
        store.ping()
    except Exception as e:  # noqa: BLE001
        log.warning("store not ready", extra={"extra_fields": {"error": str(e)}})
        raise HTTPException(status_code=503, detail="store unavailable") from e
    return {"status": "ready", "service": SERVICE}


@app.post("/orders", response_model=Order, status_code=201)
async def create_order(body: Checkout):
    cart_resp = await _call(cart_client, "cart", "GET", f"/cart/{body.cart_id}")
    if cart_resp.status_code == 404:
        raise HTTPException(status_code=404, detail="cart not found")
    if cart_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="cart returned an error")
    cart = cart_resp.json()
    if not cart["items"]:
        raise HTTPException(status_code=422, detail="cart is empty")

    lines: list[dict] = []
    currency = "USD"
    for item in cart["items"]:
        prod_resp = await _call(catalog_client, "catalog", "GET", f"/catalog/products/{item['sku']}")
        if prod_resp.status_code != 200:
            raise HTTPException(status_code=409, detail=f"sku {item['sku']} no longer available")
        product = prod_resp.json()
        if not product.get("in_stock", True):
            raise HTTPException(status_code=409, detail=f"sku {item['sku']} is out of stock")
        currency = product.get("currency", currency)
        # current catalog price wins over the cart snapshot
        lines.append(
            {
                "sku": product["sku"],
                "name": product["name"],
                "unit_price_cents": product["unit_price_cents"],
                "qty": item["qty"],
                "line_total_cents": product["unit_price_cents"] * item["qty"],
            }
        )

    order = {
        "order_id": uuid.uuid4().hex[:12].upper(),
        "cart_id": body.cart_id,
        "customer_email": body.customer_email,
        "items": lines,
        "total_cents": sum(line["line_total_cents"] for line in lines),
        "currency": currency,
        "status": "CREATED",
        "created_at": int(time.time()),
    }
    try:
        store.create(order)
    except DuplicateOrder:
        raise HTTPException(status_code=500, detail="order id collision, retry")

    try:
        await cart_client.delete(f"/cart/{body.cart_id}", headers=_headers())
    except httpx.HTTPError as e:
        log.warning("cart cleanup failed", extra={"extra_fields": {"order_id": order["order_id"], "error": str(e)}})

    log.info(
        "order created",
        extra={
            "extra_fields": {"order_id": order["order_id"], "total_cents": order["total_cents"], "lines": len(lines)}
        },
    )
    return order


@app.get("/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    order = store.get(order_id.upper())
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order
