"""Cart service: per-cart line items with prices snapshotted from the catalog.

Every add validates the SKU against the catalog service over the cluster
network (Service DNS), so the cart never holds a price the catalog did not
publish.
"""

import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from .observability import REQUEST_ID_HEADER, configure_logging, current_request_id, install_request_logging
from .store import CartStore, build_store

SERVICE = "cart"
CATALOG_URL = os.environ.get("CATALOG_URL", "http://localhost:8081").rstrip("/")
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "2.0"))

log = configure_logging(SERVICE, os.environ.get("LOG_LEVEL", "INFO"))
store: CartStore
catalog: httpx.AsyncClient


@asynccontextmanager
async def lifespan(_: FastAPI):
    global store, catalog
    store = build_store()
    catalog = httpx.AsyncClient(base_url=CATALOG_URL, timeout=HTTP_TIMEOUT)
    log.info("cart started", extra={"extra_fields": {"backend": type(store).__name__, "catalog_url": CATALOG_URL}})
    yield
    await catalog.aclose()


app = FastAPI(title="ShopStack Cart", version=os.environ.get("APP_VERSION", "dev"), lifespan=lifespan)
install_request_logging(app, log)


class AddItem(BaseModel):
    sku: str = Field(min_length=1, max_length=32)
    qty: int = Field(ge=1, le=99)


class CartLine(BaseModel):
    sku: str
    name: str
    unit_price_cents: int
    qty: int
    line_total_cents: int


class Cart(BaseModel):
    cart_id: str
    items: list[CartLine]
    subtotal_cents: int
    updated_at: int


def _view(raw: dict) -> Cart:
    lines = [
        CartLine(**item, line_total_cents=item["unit_price_cents"] * item["qty"])
        for item in sorted(raw["items"].values(), key=lambda i: i["sku"])
    ]
    return Cart(
        cart_id=raw["cart_id"],
        items=lines,
        subtotal_cents=sum(line.line_total_cents for line in lines),
        updated_at=raw["updated_at"],
    )


async def _lookup_product(sku: str) -> dict:
    try:
        resp = await catalog.get(f"/catalog/products/{sku}", headers={REQUEST_ID_HEADER: current_request_id()})
    except httpx.HTTPError as e:
        log.warning("catalog unreachable", extra={"extra_fields": {"error": str(e)}})
        raise HTTPException(status_code=503, detail="catalog service unavailable") from e
    if resp.status_code == 404:
        raise HTTPException(status_code=422, detail=f"unknown sku {sku}")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="catalog returned an error")
    product = resp.json()
    if not product.get("in_stock", True):
        raise HTTPException(status_code=409, detail=f"sku {sku} is out of stock")
    return product


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok", "service": SERVICE}


@app.get("/ready", include_in_schema=False)
def ready():
    try:
        store.ping()
    except Exception as e:  # noqa: BLE001 - any backend failure means not ready
        log.warning("store not ready", extra={"extra_fields": {"error": str(e)}})
        raise HTTPException(status_code=503, detail="store unavailable") from e
    return {"status": "ready", "service": SERVICE}


@app.get("/cart/{cart_id}", response_model=Cart)
def get_cart(cart_id: str):
    raw = store.get(cart_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="cart not found")
    return _view(raw)


@app.post("/cart/{cart_id}/items", response_model=Cart, status_code=200)
async def put_item(cart_id: str, body: AddItem):
    product = await _lookup_product(body.sku.upper())
    item = {
        "sku": product["sku"],
        "name": product["name"],
        "unit_price_cents": product["unit_price_cents"],
        "qty": body.qty,
    }
    return _view(store.put_item(cart_id, item))


@app.delete("/cart/{cart_id}/items/{sku}", response_model=Cart)
def remove_item(cart_id: str, sku: str):
    raw = store.remove_item(cart_id, sku.upper())
    if raw is None:
        raise HTTPException(status_code=404, detail="cart not found")
    return _view(raw)


@app.delete("/cart/{cart_id}", status_code=204, response_class=Response)
def delete_cart(cart_id: str):
    store.delete(cart_id)
    return Response(status_code=204)
