"""Integration tests for the webhook pipeline."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.config import Settings
from src.models import ContextCard, OpsgenieAlert, PagerDutyIncident, Severity
from src.web.store import incident_store

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


@pytest.fixture(autouse=True)
def _reset_incident_store():
    if hasattr(incident_store, "_incidents"):
        incident_store._incidents.clear()
    if hasattr(incident_store, "_order"):
        incident_store._order.clear()
    if hasattr(incident_store, "_subscribers"):
        incident_store._subscribers.clear()


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


class TestWebhookBackgroundPersistence:
    @staticmethod
    def _context_card(incident_id: str, service_name: str) -> ContextCard:
        return ContextCard(
            incident_id=incident_id,
            title="Context title",
            severity=Severity.HIGH,
            service_name=service_name,
            triggered_at=datetime.now(UTC),
            assembly_time_ms=123,
        )

    @pytest.mark.asyncio
    async def test_pagerduty_background_marks_incident_completed(self):
        from src.api.webhooks import process_pagerduty_incident_background

        incident = PagerDutyIncident(
            incident_id="pd-complete-1",
            title="PD incident",
            description="desc",
            severity=Severity.HIGH,
            service_name="payments",
            triggered_at=datetime.now(UTC),
            html_url="https://example.pagerduty.com/incidents/pd-complete-1",
        )
        settings = Settings(correlation_enabled=False)

        with patch(
            "src.api.webhooks.ContextOrchestrator.process_incident",
            new=AsyncMock(return_value=self._context_card("pd-complete-1", "payments")),
        ):
            await process_pagerduty_incident_background(incident, settings)

        stored = await incident_store.get_incident("pd-complete-1")
        assert stored is not None
        assert stored.status == "completed"
        assert stored.context_card is not None

    @pytest.mark.asyncio
    async def test_pagerduty_background_marks_incident_failed(self):
        from src.api.webhooks import process_pagerduty_incident_background

        incident = PagerDutyIncident(
            incident_id="pd-fail-1",
            title="PD incident failed",
            description="desc",
            severity=Severity.HIGH,
            service_name="payments",
            triggered_at=datetime.now(UTC),
            html_url="https://example.pagerduty.com/incidents/pd-fail-1",
        )
        settings = Settings(correlation_enabled=False)

        with patch(
            "src.api.webhooks.ContextOrchestrator.process_incident",
            new=AsyncMock(side_effect=RuntimeError("orchestrator boom")),
        ):
            await process_pagerduty_incident_background(incident, settings)

        stored = await incident_store.get_incident("pd-fail-1")
        assert stored is not None
        assert stored.status == "error"
        assert stored.error_message is not None
        assert "orchestrator boom" in stored.error_message

    @pytest.mark.asyncio
    async def test_opsgenie_background_marks_incident_completed(self):
        from src.api.webhooks import process_opsgenie_alert_background

        alert = OpsgenieAlert(
            alert_id="og-complete-1",
            title="OG alert",
            description="desc",
            severity=Severity.HIGH,
            service_name="checkout",
            triggered_at=datetime.now(UTC),
            url="https://example.app.opsgenie.com/alert/detail/og-complete-1/details",
        )
        settings = Settings(correlation_enabled=False)

        with patch(
            "src.api.webhooks.ContextOrchestrator.process_incident",
            new=AsyncMock(return_value=self._context_card("og-complete-1", "checkout")),
        ):
            await process_opsgenie_alert_background(alert, settings)

        stored = await incident_store.get_incident("og-complete-1")
        assert stored is not None
        assert stored.status == "completed"
        assert stored.context_card is not None

    @pytest.mark.asyncio
    async def test_opsgenie_background_marks_incident_failed(self):
        from src.api.webhooks import process_opsgenie_alert_background

        alert = OpsgenieAlert(
            alert_id="og-fail-1",
            title="OG alert failed",
            description="desc",
            severity=Severity.HIGH,
            service_name="checkout",
            triggered_at=datetime.now(UTC),
            url="https://example.app.opsgenie.com/alert/detail/og-fail-1/details",
        )
        settings = Settings(correlation_enabled=False)

        with patch(
            "src.api.webhooks.ContextOrchestrator.process_incident",
            new=AsyncMock(side_effect=RuntimeError("opsgenie orchestrator boom")),
        ):
            await process_opsgenie_alert_background(alert, settings)

        stored = await incident_store.get_incident("og-fail-1")
        assert stored is not None
        assert stored.status == "error"
        assert stored.error_message is not None
        assert "opsgenie orchestrator boom" in stored.error_message

    @pytest.mark.asyncio
    async def test_pagerduty_background_fail_incident_happens_before_error_log(self):
        from src.api.webhooks import process_pagerduty_incident_background

        incident = PagerDutyIncident(
            incident_id="pd-fail-order-1",
            title="PD incident failed order",
            description="desc",
            severity=Severity.HIGH,
            service_name="payments",
            triggered_at=datetime.now(UTC),
            html_url="https://example.pagerduty.com/incidents/pd-fail-order-1",
        )
        settings = Settings(correlation_enabled=False)
        calls: list[tuple[str, str]] = []

        async def _fail(incident_id: str, error_message: str = "", **kwargs):
            calls.append(("fail", incident_id))

        def _error(_event: str, **kwargs):
            calls.append(("log", kwargs["incident_id"]))

        with (
            patch(
                "src.api.webhooks.ContextOrchestrator.process_incident",
                new=AsyncMock(side_effect=RuntimeError("order boom")),
            ),
            patch("src.api.webhooks.incident_store.fail_incident", new=AsyncMock(side_effect=_fail)),
            patch("src.api.webhooks.logger.error", side_effect=_error),
        ):
            await process_pagerduty_incident_background(incident, settings)

        assert calls == [("fail", "pd-fail-order-1"), ("log", "pd-fail-order-1")]

    @pytest.mark.asyncio
    async def test_opsgenie_background_uses_same_incident_id_for_add_and_fail(self):
        from src.api.webhooks import process_opsgenie_alert_background

        alert = OpsgenieAlert(
            alert_id="og-fail-order-1",
            title="OG alert failed order",
            description="desc",
            severity=Severity.HIGH,
            service_name="checkout",
            triggered_at=datetime.now(UTC),
            url="https://example.app.opsgenie.com/alert/detail/og-fail-order-1/details",
        )
        settings = Settings(correlation_enabled=False)
        calls: list[tuple[str, str]] = []

        async def _add(incident_id: str, **_kwargs):
            calls.append(("add", incident_id))

        async def _fail(incident_id: str, error_message: str = "", **kwargs):
            calls.append(("fail", incident_id))

        def _error(_event: str, **kwargs):
            calls.append(("log", kwargs["alert_id"]))

        with (
            patch("src.api.webhooks.incident_store.add_incident", new=AsyncMock(side_effect=_add)),
            patch(
                "src.api.webhooks.ContextOrchestrator.process_incident",
                new=AsyncMock(side_effect=RuntimeError("ops order boom")),
            ),
            patch("src.api.webhooks.incident_store.fail_incident", new=AsyncMock(side_effect=_fail)),
            patch("src.api.webhooks.logger.error", side_effect=_error),
        ):
            await process_opsgenie_alert_background(alert, settings)

        assert calls[0] == ("add", "og-fail-order-1")
        assert calls[1] == ("fail", "og-fail-order-1")
        assert calls[2] == ("log", "og-fail-order-1")


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
