"""Integration tests for the webhook pipeline."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone


# Test PagerDuty webhook payload
PAGERDUTY_V3_PAYLOAD = {
    "event": {
        "event_type": "incident.triggered",
        "data": {
            "id": "TEST001",
            "incident_number": 1,
            "title": "High CPU on web-api-prod-01",
            "description": "CPU at 95% for 10 minutes",
            "urgency": "high",
            "created_at": "2026-02-16T10:00:00Z",
            "html_url": "https://exciting.pagerduty.com/incidents/TEST001",
            "service": {"id": "PSVC001", "summary": "web-api"},
            "assignments": [{"assignee": {"summary": "James Xu"}}],
        },
    }
}

PAGERDUTY_RESOLVE_PAYLOAD = {
    "event": {
        "event_type": "incident.resolved",
        "data": {"id": "TEST001", "service": {"summary": "web-api"}},
    }
}


class TestPagerDutyWebhook:
    """Test PagerDuty webhook endpoint."""

    @pytest.mark.asyncio
    async def test_valid_incident_trigger(self):
        """Valid PD incident should return 200 with accepted status."""
        from httpx import ASGITransport, AsyncClient
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/webhooks/pagerduty", json=PAGERDUTY_V3_PAYLOAD)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["incident_id"] == "TEST001"
            assert data["service"] == "web-api"

    @pytest.mark.asyncio
    async def test_non_trigger_event_ignored(self):
        """Non-trigger events should be ignored."""
        from httpx import ASGITransport, AsyncClient
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/pagerduty", json=PAGERDUTY_RESOLVE_PAYLOAD
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        """Invalid JSON should return 400."""
        from httpx import ASGITransport, AsyncClient
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/pagerduty",
                content=b"not json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Health check should return 200."""
        from httpx import ASGITransport, AsyncClient
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/webhooks/health")
            assert resp.status_code == 200


class TestAIAdapter:
    """Test AI adapter layer."""

    def test_verdict_engine_orchestrator_kwargs(self):
        """VerdictEngine should handle orchestrator-style kwargs."""
        from src.ai.adapter import VerdictEngine

        engine = VerdictEngine()
        # Just verify it instantiates without error
        assert engine is not None

    def test_log_summarizer_init(self):
        """LogSummarizer should instantiate."""
        from src.ai.adapter import LogSummarizer

        summarizer = LogSummarizer()
        assert summarizer is not None

    def test_stub_fallback(self):
        """AI client stubs should work when service URL is empty."""
        import os

        from src.ai.client import AIServiceClient

        old = os.environ.get("AI_SERVICE_URL", "")
        os.environ["AI_SERVICE_URL"] = ""
        client = AIServiceClient()
        assert not client.enabled
        result = client._stub_summary([{"message": "error", "level": "error"}])
        assert "summary" in result
        os.environ["AI_SERVICE_URL"] = old
