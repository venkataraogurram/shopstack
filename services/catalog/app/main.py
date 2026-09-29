"""Catalog service: read-only product listing.

Products are loaded from a JSON file at startup. In Kubernetes the file is
mounted from a ConfigMap, so the catalog can be updated without rebuilding
the image.
"""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .observability import configure_logging, install_request_logging

SERVICE = "catalog"
CATALOG_FILE = Path(os.environ.get("CATALOG_FILE", Path(__file__).with_name("products.json")))
CURRENCY = os.environ.get("CURRENCY", "USD")

log = configure_logging(SERVICE, os.environ.get("LOG_LEVEL", "INFO"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _products
    _products = load_products(CATALOG_FILE)
    log.info("catalog loaded", extra={"extra_fields": {"file": str(CATALOG_FILE), "count": len(_products)}})
    yield


app = FastAPI(title="ShopStack Catalog", version=os.environ.get("APP_VERSION", "dev"), lifespan=lifespan)
install_request_logging(app, log)


class Product(BaseModel):
    sku: str
    name: str
    description: str = ""
    unit_price_cents: int = Field(ge=0)
    currency: str = CURRENCY
    in_stock: bool = True


_products: dict[str, Product] = {}


def load_products(path: Path) -> dict[str, Product]:
    with path.open() as f:
        raw = json.load(f)
    products = {p["sku"]: Product(**p) for p in raw}
    if not products:
        raise ValueError(f"no products found in {path}")
    return products


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok", "service": SERVICE}


@app.get("/ready", include_in_schema=False)
def ready():
    if not _products:
        raise HTTPException(status_code=503, detail="catalog not loaded")
    return {"status": "ready", "service": SERVICE, "products": len(_products)}


@app.get("/catalog/products", response_model=list[Product])
def list_products(in_stock: bool | None = None):
    items = _products.values()
    if in_stock is not None:
        items = (p for p in items if p.in_stock == in_stock)
    return sorted(items, key=lambda p: p.sku)


@app.get("/catalog/products/{sku}", response_model=Product)
def get_product(sku: str):
    product = _products.get(sku.upper())
    if product is None:
        raise HTTPException(status_code=404, detail=f"unknown sku {sku}")
    return product
