import httpx
import pytest
from fastapi.testclient import TestClient

from app import main

PRODUCTS = {
    "TSH-001": {"sku": "TSH-001", "name": "Classic Cotton T-Shirt", "unit_price_cents": 1999, "in_stock": True},
    "BLT-007": {"sku": "BLT-007", "name": "Leather Belt", "unit_price_cents": 2999, "in_stock": False},
}


def fake_catalog(request: httpx.Request) -> httpx.Response:
    sku = request.url.path.rsplit("/", 1)[-1]
    if sku in PRODUCTS:
        return httpx.Response(200, json=PRODUCTS[sku])
    return httpx.Response(404, json={"detail": "unknown sku"})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STORE_BACKEND", "memory")
    with TestClient(main.app) as c:
        # swap the real catalog client for an in-process fake
        main.catalog = httpx.AsyncClient(transport=httpx.MockTransport(fake_catalog), base_url="http://catalog")
        yield c


def test_add_get_remove(client):
    r = client.post("/cart/c1/items", json={"sku": "tsh-001", "qty": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["items"][0]["line_total_cents"] == 3998
    assert body["subtotal_cents"] == 3998

    assert client.get("/cart/c1").json()["subtotal_cents"] == 3998

    r = client.delete("/cart/c1/items/TSH-001")
    assert r.status_code == 200 and r.json()["items"] == []

    assert client.delete("/cart/c1").status_code == 204
    assert client.get("/cart/c1").status_code == 404


def test_validation_errors(client):
    assert client.post("/cart/c2/items", json={"sku": "NOPE-1", "qty": 1}).status_code == 422
    assert client.post("/cart/c2/items", json={"sku": "BLT-007", "qty": 1}).status_code == 409
    assert client.post("/cart/c2/items", json={"sku": "TSH-001", "qty": 0}).status_code == 422
    assert client.get("/cart/missing").status_code == 404
    assert client.delete("/cart/missing/items/TSH-001").status_code == 404


def test_catalog_down_returns_503(client):
    def boom(request):
        raise httpx.ConnectError("refused")

    main.catalog = httpx.AsyncClient(transport=httpx.MockTransport(boom), base_url="http://catalog")
    assert client.post("/cart/c3/items", json={"sku": "TSH-001", "qty": 1}).status_code == 503
