"""Tests for webhook Prometheus metrics instrumentation."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _get_counter_value(
    metrics_text: str, metric_name: str, labels: dict[str, str]
) -> float:
    """Parse a Prometheus counter sample value for an exact set of labels."""

    # Example:
    # incident_copilot_webhook_requests_total{source="pagerduty",status="success"} 3.0
    label_str = ",".join([f'{k}="{v}"' for k, v in labels.items()])
    pattern = (
        rf"^{re.escape(metric_name)}\{{{re.escape(label_str)}\}}\s+([0-9eE+\-.]+)$"
    )
    for line in metrics_text.splitlines():
        m = re.match(pattern, line)
        if m:
            return float(m.group(1))
    return 0.0


class TestWebhookMetrics:
    def test_pagerduty_invalid_json_increments_invalid(self, client: TestClient):
        before = client.get("/metrics").text
        before_val = _get_counter_value(
            before,
            "incident_copilot_webhook_requests_total",
            {"source": "pagerduty", "status": "invalid"},
        )

        resp = client.post(
            "/webhooks/pagerduty",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

        after = client.get("/metrics").text
        after_val = _get_counter_value(
            after,
            "incident_copilot_webhook_requests_total",
            {"source": "pagerduty", "status": "invalid"},
        )
        assert after_val >= before_val + 1

    def test_pagerduty_non_trigger_increments_success(self, client: TestClient):
        before = client.get("/metrics").text
        before_val = _get_counter_value(
            before,
            "incident_copilot_webhook_requests_total",
            {"source": "pagerduty", "status": "success"},
        )

        payload = {
            "event": {
                "event_type": "incident.acknowledged",
                "data": {"id": "P123"},
            }
        }
        resp = client.post("/webhooks/pagerduty", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

        after = client.get("/metrics").text
        after_val = _get_counter_value(
            after,
            "incident_copilot_webhook_requests_total",
            {"source": "pagerduty", "status": "success"},
        )
        assert after_val >= before_val + 1

    def test_opsgenie_non_create_increments_success(self, client: TestClient):
        before = client.get("/metrics").text
        before_val = _get_counter_value(
            before,
            "incident_copilot_webhook_requests_total",
            {"source": "opsgenie", "status": "success"},
        )

        payload = {
            "action": "Acknowledge",
            "alert": {
                "alertId": "A123",
                "message": "Test",
                "priority": "P3",
            },
        }
        resp = client.post("/webhooks/opsgenie", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

        after = client.get("/metrics").text
        after_val = _get_counter_value(
            after,
            "incident_copilot_webhook_requests_total",
            {"source": "opsgenie", "status": "success"},
        )
        assert after_val >= before_val + 1
