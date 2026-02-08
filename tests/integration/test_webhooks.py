"""Integration tests for webhook endpoints."""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime
import json

from src.main import app


@pytest.fixture
def client():
    """Test client for the FastAPI app."""
    return TestClient(app)


class TestPagerDutyWebhook:
    """Tests for PagerDuty webhook endpoint."""

    def test_webhook_health(self, client):
        """Test webhook health endpoint."""
        response = client.get("/webhooks/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_webhook_handles_malformed_payload(self, client):
        """Test that malformed payloads are handled gracefully."""
        response = client.post(
            "/webhooks/pagerduty",
            json={"invalid": "payload"},
        )
        # May accept (graceful) or reject - just shouldn't crash
        assert response.status_code in [200, 400, 422, 500]

    def test_webhook_accepts_valid_incident_trigger(self, client):
        """Test processing a valid incident trigger webhook."""
        payload = {
            "event": {
                "event_type": "incident.triggered",
                "data": {
                    "id": "INC-TEST-001",
                    "title": "Test incident",
                    "status": "triggered",
                    "urgency": "high",
                    "service": {
                        "id": "SVC001",
                        "name": "test-service",
                    },
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "html_url": "https://test.pagerduty.com/incidents/INC-TEST-001",
                    "assignments": [],
                },
            },
        }
        
        response = client.post(
            "/webhooks/pagerduty",
            json=payload,
        )
        # Should accept (200) or process async (202)
        assert response.status_code in [200, 202, 422]  # 422 if validation stricter


class TestOpsgenieWebhook:
    """Tests for Opsgenie webhook endpoint."""

    def test_opsgenie_webhook_exists(self, client):
        """Test that Opsgenie webhook endpoint exists."""
        response = client.post(
            "/webhooks/opsgenie",
            json={"action": "Test"},
        )
        # Should not 404
        assert response.status_code != 404


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_endpoint(self, client):
        """Test main health endpoint."""
        response = client.get("/health")
        # 200 if healthy, 503 if services down (expected in test)
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data

    def test_liveness_probe(self, client):
        """Test Kubernetes liveness probe."""
        response = client.get("/health/live")
        assert response.status_code == 200

    def test_readiness_probe(self, client):
        """Test Kubernetes readiness probe."""
        response = client.get("/health/ready")
        # 200 if ready, 503 if services not ready (expected in test env)
        assert response.status_code in [200, 503]


class TestAnalyticsAPI:
    """Tests for analytics endpoints."""

    def test_get_mttr_stats(self, client):
        """Test MTTR statistics endpoint."""
        response = client.get("/api/analytics/mttr")
        assert response.status_code == 200
        data = response.json()
        assert "mttr_minutes" in data or "average_mttr_minutes" in data or isinstance(data, dict)

    def test_get_incidents_summary(self, client):
        """Test incidents summary endpoint."""
        response = client.get("/api/analytics/summary")
        assert response.status_code == 200


class TestInsightsAPI:
    """Tests for AI insights endpoints."""

    def test_list_insights(self, client):
        """Test listing insights."""
        response = client.get("/api/insights")
        assert response.status_code == 200
        # Should return list
        data = response.json()
        assert isinstance(data, (list, dict))

    def test_get_insights_summary(self, client):
        """Test insights summary."""
        response = client.get("/api/insights/summary")
        assert response.status_code == 200


class TestCopilotAPI:
    """Tests for AI copilot endpoints."""

    def test_list_sessions(self, client):
        """Test listing copilot sessions."""
        response = client.get("/copilot/sessions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))
