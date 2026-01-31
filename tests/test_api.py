"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_root(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Incident Copilot"
    assert data["status"] == "running"


def test_health(client):
    """Test health check endpoint."""
    response = client.get("/webhooks/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_pagerduty_webhook_invalid_json(client):
    """Test webhook rejects invalid JSON."""
    response = client.post(
        "/webhooks/pagerduty",
        content="not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400


def test_pagerduty_webhook_non_trigger_event(client):
    """Test webhook ignores non-trigger events."""
    payload = {
        "event": {
            "event_type": "incident.acknowledged",
            "data": {"id": "P123"},
        }
    }

    response = client.post("/webhooks/pagerduty", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
