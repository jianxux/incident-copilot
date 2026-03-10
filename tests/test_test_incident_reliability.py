"""Tests for test incident reliability improvements."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import AILogSummary, ContextCard, PagerDutyIncident, Severity
from src.onboarding.test_incident import _process


def _make_incident(incident_id: str = "test-123") -> PagerDutyIncident:
    return PagerDutyIncident(
        incident_id=incident_id,
        title="[TEST] Test incident",
        description="Test",
        severity=Severity.HIGH,
        service_name="payments-api",
        triggered_at=datetime.now(UTC),
        html_url="http://localhost/incident/test-123",
    )


def _make_card(incident_id: str = "test-123") -> ContextCard:
    return ContextCard(
        incident_id=incident_id,
        title="[TEST] Test incident",
        severity=Severity.HIGH,
        service_name="payments-api",
        triggered_at=datetime.now(UTC),
        alert_url="http://localhost/incident/test-123",
        assembly_time_ms=100,
    )


class TestProcessReliability:
    """Test _process function handles failures gracefully."""

    @pytest.mark.asyncio
    async def test_successful_processing(self):
        """Normal path: orchestrator succeeds, incident marked completed."""
        incident = _make_incident()
        card = _make_card()

        mock_orchestrator = MagicMock()
        mock_orchestrator.process_incident = AsyncMock(return_value=card)

        with (
            patch("src.onboarding.test_incident.ContextOrchestrator", return_value=mock_orchestrator),
            patch("src.onboarding.test_incident.incident_store") as mock_store,
        ):
            mock_store.complete_incident = AsyncMock()
            await _process(incident, None, "tenant-1")

            mock_store.complete_incident.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_orchestrator_failure_creates_fallback(self):
        """When orchestrator fails, a fallback card is created."""
        incident = _make_incident()

        mock_orchestrator = MagicMock()
        mock_orchestrator.process_incident = AsyncMock(side_effect=Exception("API error"))

        with (
            patch("src.onboarding.test_incident.ContextOrchestrator", return_value=mock_orchestrator),
            patch("src.onboarding.test_incident.incident_store") as mock_store,
        ):
            mock_store.complete_incident = AsyncMock()
            await _process(incident, None, "tenant-1")

            # Should have called complete_incident with a fallback card
            mock_store.complete_incident.assert_awaited_once()
            call_kwargs = mock_store.complete_incident.call_args
            metadata = call_kwargs.kwargs.get("metadata") or call_kwargs[1].get("metadata", {})
            assert metadata.get("fallback") is True

    @pytest.mark.asyncio
    async def test_fallback_store_failure_keeps_processing_state(self):
        """When fallback persistence fails, verify the incident is still visible."""
        incident = _make_incident()

        mock_orchestrator = MagicMock()
        mock_orchestrator.process_incident = AsyncMock(side_effect=Exception("API error"))

        with (
            patch("src.onboarding.test_incident.ContextOrchestrator", return_value=mock_orchestrator),
            patch("src.onboarding.test_incident.incident_store") as mock_store,
        ):
            mock_store.complete_incident = AsyncMock(side_effect=Exception("DB write failed"))
            mock_store.get_incident = AsyncMock(
                return_value=MagicMock(incident_id=incident.incident_id, status="processing")
            )
            await _process(incident, None, "tenant-1")

            mock_store.get_incident.assert_awaited_once_with(
                incident.incident_id, tenant_id="tenant-1"
            )

    @pytest.mark.asyncio
    async def test_timeout_produces_clear_error(self):
        """When orchestrator times out, error message mentions timeout."""
        incident = _make_incident()

        async def slow_process(*args, **kwargs):
            await asyncio.sleep(999)

        mock_orchestrator = MagicMock()
        mock_orchestrator.process_incident = slow_process

        with (
            patch("src.onboarding.test_incident.ContextOrchestrator", return_value=mock_orchestrator),
            patch("src.onboarding.test_incident.incident_store") as mock_store,
            patch("src.onboarding.test_incident._PROCESS_TIMEOUT_SECONDS", 0.1),
        ):
            mock_store.complete_incident = AsyncMock()
            await _process(incident, None, "tenant-1")

            # Should complete with a fallback mentioning timeout
            mock_store.complete_incident.assert_awaited_once()
            call_args = mock_store.complete_incident.call_args
            card = call_args[0][1]  # second positional arg is the context_card
            assert any("timed out" in err.lower() for err in (card.errors or []))
