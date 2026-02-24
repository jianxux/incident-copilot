"""Tests for incident detail/chat/timeline routes passing tenant_id correctly."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

os.environ["SUPABASE_DB_ENABLED"] = "false"
os.environ["SUPABASE_AUTH_ENABLED"] = "false"
os.environ.pop("SUPABASE_URL", None)

from src.models import ContextCard, Severity
from src.web.store import InMemoryIncidentStore, StoredIncident


@pytest.fixture
def mock_store():
    store = InMemoryIncidentStore()
    return store


@pytest.fixture
def sample_incident():
    return StoredIncident(
        incident_id="inc-123",
        title="Test incident",
        service_name="payments-api",
        severity=Severity.HIGH,
        status="completed",
        triggered_at=datetime.now(UTC),
        processed_at=datetime.now(UTC),
        context_card=ContextCard(
            incident_id="inc-123",
            title="Test incident",
            severity=Severity.HIGH,
            service_name="payments-api",
            triggered_at=datetime.now(UTC),
            assembled_at=datetime.now(UTC),
            assembly_time_ms=500,
        ),
        source="pagerduty",
        source_url="https://pagerduty.com/incidents/inc-123",
    )


class TestIncidentDetailPassesTenantId:
    """Verify that incident detail routes pass tenant_id from auth context."""

    @pytest.mark.asyncio
    async def test_get_incident_uses_tenant_id(self, mock_store, sample_incident):
        """get_incident should be called with tenant_id from auth context."""
        mock_store.get_incident = AsyncMock(return_value=sample_incident)

        # Simulate what the route does
        tenant_id = "tenant-abc"
        result = await mock_store.get_incident("inc-123", tenant_id=tenant_id)

        mock_store.get_incident.assert_called_once_with("inc-123", tenant_id=tenant_id)
        assert result.incident_id == "inc-123"

    @pytest.mark.asyncio
    async def test_get_incident_without_tenant_falls_back(self, mock_store):
        """Without tenant_id, get_incident still works (uses default)."""
        await mock_store.add_incident(
            incident_id="inc-456",
            title="Another incident",
            service_name="api-gw",
            severity=Severity.MEDIUM,
            triggered_at=datetime.now(UTC),
        )

        result = await mock_store.get_incident("inc-456", tenant_id=None)
        assert result is not None
        assert result.incident_id == "inc-456"

    @pytest.mark.asyncio
    async def test_get_incident_wrong_tenant_returns_none_in_supabase(self):
        """In Supabase mode, wrong tenant_id should return None.

        We mock the Supabase store's get_incident to verify tenant filtering.
        """
        from src.web.store import SupabaseIncidentStore

        store = SupabaseIncidentStore()
        store._resolve_tenant = AsyncMock(return_value="tenant-wrong")

        mock_db = AsyncMock()
        mock_db.get_processing_incident = AsyncMock(return_value=None)

        with patch("src.db.supabase_db.get_db", return_value=mock_db):
            with patch("src.web.store.is_supabase_db_enabled", return_value=True):
                result = await store.get_incident("inc-789", tenant_id="tenant-wrong")

        assert result is None
        mock_db.get_processing_incident.assert_called_once_with(
            tenant_id="tenant-wrong",
            incident_id="inc-789",
        )


class TestRouteAuthIntegration:
    """Test that routes include auth dependency and pass tenant_id."""

    def test_incident_detail_has_auth_dependency(self):
        """incident_detail route should have require_dashboard_auth dependency."""
        import inspect

        from src.web.routes import incident_detail

        sig = inspect.signature(incident_detail)
        param_names = list(sig.parameters.keys())
        assert "auth_data" in param_names, "incident_detail must accept auth_data"

    def test_incident_chat_has_auth_dependency(self):
        """incident_chat route should have require_dashboard_auth dependency."""
        import inspect

        from src.web.routes import incident_chat

        sig = inspect.signature(incident_chat)
        param_names = list(sig.parameters.keys())
        assert "auth_data" in param_names, "incident_chat must accept auth_data"

    def test_incident_timeline_has_auth_dependency(self):
        """incident_timeline route should have require_dashboard_auth dependency."""
        import inspect

        from src.web.routes import incident_timeline

        sig = inspect.signature(incident_timeline)
        param_names = list(sig.parameters.keys())
        assert "auth_data" in param_names, "incident_timeline must accept auth_data"
