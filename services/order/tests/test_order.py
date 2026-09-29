import httpx
import pytest
from fastapi.testclient import TestClient

from app import main

CARTS = {
    "c1": {
        "cart_id": "c1",
        "updated_at": 1,
        "subtotal_cents": 3998,
        "items": [
            {
                "sku": "TSH-001",
                "name": "Classic Cotton T-Shirt",
                "unit_price_cents": 1899,
                "qty": 2,
                "line_total_cents": 3798,
            }
        ],
    },
    "empty": {"cart_id": "empty", "updated_at": 1, "subtotal_cents": 0, "items": []},
    "gone": {
        "cart_id": "gone",
        "updated_at": 1,
        "subtotal_cents": 100,
        "items": [
            {"sku": "BLT-007", "name": "Leather Belt", "unit_price_cents": 2999, "qty": 1, "line_total_cents": 2999}
        ],
    },
}
PRODUCTS = {
    "TSH-001": {
        "sku": "TSH-001",
        "name": "Classic Cotton T-Shirt",
        "unit_price_cents": 1999,
        "currency": "USD",
        "in_stock": True,
    },
    "BLT-007": {
        "sku": "BLT-007",
        "name": "Leather Belt",
        "unit_price_cents": 2999,
        "currency": "USD",
        "in_stock": False,
    },
}
deleted_carts: list[str] = []


def fake_cart(request: httpx.Request) -> httpx.Response:
    cart_id = request.url.path.rsplit("/", 1)[-1]
    if request.method == "DELETE":
        deleted_carts.append(cart_id)
        return httpx.Response(204)
    if cart_id in CARTS:
        return httpx.Response(200, json=CARTS[cart_id])
    return httpx.Response(404, json={"detail": "cart not found"})


def fake_catalog(request: httpx.Request) -> httpx.Response:
    sku = request.url.path.rsplit("/", 1)[-1]
    if sku in PRODUCTS:
        return httpx.Response(200, json=PRODUCTS[sku])
    return httpx.Response(404, json={"detail": "unknown sku"})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STORE_BACKEND", "memory")
    deleted_carts.clear()
    with TestClient(main.app) as c:
        main.cart_client = httpx.AsyncClient(transport=httpx.MockTransport(fake_cart), base_url="http://cart")
        main.catalog_client = httpx.AsyncClient(transport=httpx.MockTransport(fake_catalog), base_url="http://catalog")
        yield c


def test_checkout_uses_current_catalog_price_and_clears_cart(client):
    r = client.post("/orders", json={"cart_id": "c1", "customer_email": "a@example.com"})
    assert r.status_code == 201
    order = r.json()
    assert order["status"] == "CREATED"
    assert order["total_cents"] == 2 * 1999  # catalog price, not the 1899 cart snapshot
    assert deleted_carts == ["c1"]

    fetched = client.get(f"/orders/{order['order_id'].lower()}")
    assert fetched.status_code == 200 and fetched.json()["order_id"] == order["order_id"]


def test_checkout_errors(client):
    assert client.post("/orders", json={"cart_id": "nope", "customer_email": "a@example.com"}).status_code == 404
    assert client.post("/orders", json={"cart_id": "empty", "customer_email": "a@example.com"}).status_code == 422
    assert client.post("/orders", json={"cart_id": "gone", "customer_email": "a@example.com"}).status_code == 409
    assert client.get("/orders/MISSING").status_code == 404


def test_cart_service_down(client):
    def boom(request):
        raise httpx.ConnectTimeout("timeout")

    main.cart_client = httpx.AsyncClient(transport=httpx.MockTransport(boom), base_url="http://cart")
    assert client.post("/orders", json={"cart_id": "c1", "customer_email": "a@example.com"}).status_code == 503
