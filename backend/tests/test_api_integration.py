from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_ok() -> None:
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_contains_mvp_endpoints() -> None:
    paths = TestClient(app).get("/openapi.json").json()["paths"]

    assert "/api/v1/food-items" in paths
    assert "/api/v1/food-images" in paths
    assert "/api/v1/analysis-jobs" in paths
    assert "/api/v1/dashboard/summary" in paths
    assert "/api/v1/food-items/{item_id}/cooking-status" in paths


def test_invalid_food_payload_is_rejected_before_db_access() -> None:
    response = TestClient(app).post(
        "/api/v1/food-items",
        json={"display_name": "", "storage_type": "invalid"},
    )

    assert response.status_code == 422
