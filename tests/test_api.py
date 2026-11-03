
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import main


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        return None


class FakeEngine:
    def connect(self):
        return FakeConnection()

    def dispose(self):
        pass


@pytest.fixture
def client(monkeypatch):
    # Mock database access so tests never modify PostgreSQL.
    monkeypatch.setattr(main, "rows", lambda sql, params=None: [])
    monkeypatch.setattr(main, "one", lambda sql, params=None: {})

    # Health endpoint also receives a mocked database connection.
    monkeypatch.setattr(main, "engine", FakeEngine())

    with TestClient(main.app) as test_client:
        yield test_client


def test_root_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["name"] == "HORIZON Analytics API"


def test_health_endpoint(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "connected"


def test_overview_endpoint(client):
    response = client.get("/api/overview")

    assert response.status_code == 200
    assert "billing_source" in response.json()
    assert "independent_churn_source" in response.json()


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/revenue/monthly",
        "/api/revenue/regions",
        "/api/revenue/plans",
        "/api/revenue/invoice-status",
        "/api/churn/features",
        "/api/churn/segments",
        "/api/churn/numeric-bands",
        "/api/churn/customers",
    ],
)
def test_analytics_list_endpoints(client, endpoint):
    response = client.get(endpoint)

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_revenue_accounts_pagination(client):
    response = client.get(
        "/api/revenue/accounts?limit=10&offset=5"
    )

    assert response.status_code == 200
    assert response.json() == []


def test_revenue_accounts_rejects_invalid_limit(client):
    response = client.get("/api/revenue/accounts?limit=500")

    assert response.status_code == 422


def test_churn_summary_endpoint(client):
    response = client.get("/api/churn/summary")

    assert response.status_code == 200
    assert "distribution" in response.json()
    assert "priority_tiers" in response.json()
    assert "model_note" in response.json()


def test_churn_segments_filter(client):
    response = client.get(
        "/api/churn/segments?dimension=industry"
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_churn_customer_count(client):
    response = client.get("/api/churn/customers/count")

    assert response.status_code == 200


def test_churn_batch_model_info(client):
    response = client.get("/api/churn/batch-model-info")

    assert response.status_code == 200


def test_churn_model_info(client):
    response = client.get("/api/churn/model-info")

    assert response.status_code == 200

    data = response.json()
    assert data["model_version"] == "1.0.0-calibrated"
    assert data["threshold"] == 0.075
    assert data["calibrated"] is True


def test_metadata_sources(client):
    response = client.get("/api/metadata/sources")

    assert response.status_code == 200
    assert len(response.json()["sources"]) == 3


def test_prediction_endpoint(client, monkeypatch):
    class FakeModel:
        def predict_proba(self, frame):
            assert len(frame) == 1
            return [[0.90, 0.10]]

    monkeypatch.setattr(
        main,
        "load_churn_model",
        lambda: FakeModel()
    )

    response = client.post(
        "/api/churn/predict",
        json={
            "monthly_recurring_revenue": 499,
            "active_seats_used": 8,
            "total_seats_allowed": 10,
            "support_tickets_30d": 5,
            "feature_adoption_rate": 0.35,
            "industry": "FinTech",
            "country": "India",
            "company_size": "Medium",
            "account_manager": "AM_12",
            "plan_tier": "Pro",
            "billing_cycle": "Monthly",
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["predicted_churn_probability"] == 0.10
    assert data["threshold"] == 0.075
    assert data["decision"] == "flag_for_review"
    assert data["model_version"] == "1.0.0-calibrated"


def test_prediction_rejects_invalid_adoption_rate(client):
    response = client.post(
        "/api/churn/predict",
        json={"feature_adoption_rate": 1.5},
    )

    assert response.status_code == 422


def test_prediction_rejects_payment_status(client):
    response = client.post(
        "/api/churn/predict",
        json={"payment_status": "Active"},
    )

    assert response.status_code == 422
