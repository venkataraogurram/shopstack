from fastapi.testclient import TestClient

from app.main import app


def test_health_and_ready():
    with TestClient(app) as client:
        assert client.get("/healthz").json()["status"] == "ok"
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["products"] > 0


def test_list_and_get_product():
    with TestClient(app) as client:
        products = client.get("/catalog/products").json()
        assert products and products[0]["sku"] == "BAG-008"
        one = client.get("/catalog/products/tsh-001")
        assert one.status_code == 200
        assert one.json()["unit_price_cents"] == 1999
        assert "X-Request-ID" in one.headers


def test_in_stock_filter_and_unknown_sku():
    with TestClient(app) as client:
        out_of_stock = client.get("/catalog/products", params={"in_stock": "false"}).json()
        assert [p["sku"] for p in out_of_stock] == ["BLT-007"]
        assert client.get("/catalog/products/NOPE-999").status_code == 404
