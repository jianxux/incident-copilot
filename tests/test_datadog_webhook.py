"""Tests for Datadog webhook endpoint."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_datadog_webhook_valid_payload(client):
    payload = {
        "id": "dd-alert-123",
        "title": "High CPU usage on payments-api",
        "text": "CPU usage exceeded 90% threshold",
        "status": "Alert",
        "alert_type": "error",
        "date": 1705312200,
        "tags": ["service:payments-api", "env:production"],
        "link": "https://app.datadoghq.com/monitors/123",
    }

    with patch("src.api.webhooks.get_settings", return_value=Settings()):
        response = client.post("/webhooks/datadog", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["service"] == "payments-api"


def test_datadog_webhook_invalid_json(client):
    with patch("src.api.webhooks.get_settings", return_value=Settings()):
        response = client.post(
            "/webhooks/datadog",
            content="not json",
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 400


def test_datadog_webhook_invalid_token(client):
    settings = Settings(datadog_webhook_token="secret-token")
    payload = {"status": "Alert", "title": "Test", "id": "dd-1"}

    with patch("src.api.webhooks.get_settings", return_value=settings):
        response = client.post(
            "/webhooks/datadog",
            json=payload,
            headers={"X-Webhook-Token": "wrong-token"},
        )

    assert response.status_code == 401


def test_datadog_webhook_invalid_signature(client):
    settings = Settings(datadog_webhook_secret="secret-signature")
    payload = {"status": "Alert", "title": "Test", "id": "dd-2"}

    with patch("src.api.webhooks.get_settings", return_value=settings):
        response = client.post(
            "/webhooks/datadog",
            json=payload,
            headers={"X-Datadog-Signature": "bad-signature"},
        )

    assert response.status_code == 401
