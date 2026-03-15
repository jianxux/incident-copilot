from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from src.models import ContextCard

import pytest


@pytest.mark.anyio
async def test_start_test_incident_uses_explicit_tenant(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    import src.config as config_module
    import src.db.supabase_db as supabase_db
    import src.onboarding.test_incident as test_incident_module
    import src.supabase_client as supabase_client_module
    from src.onboarding.test_incident import start_test_incident
    from src.web.store import SupabaseIncidentStore

    config_module.get_settings.cache_clear()
    supabase_client_module.is_supabase_db_enabled.cache_clear()

    fake_db = AsyncMock()
    fake_db.ensure_tenant = AsyncMock(return_value={"id": "default-tenant"})
    fake_db.upsert_processing_incident = AsyncMock()

    monkeypatch.setattr(supabase_db, "get_db", lambda use_admin=True: fake_db)

    def _fake_create_task(coro):
        coro.close()
        return AsyncMock()

    monkeypatch.setattr(test_incident_module.asyncio, "create_task", _fake_create_task)
    monkeypatch.setattr(test_incident_module, "incident_store", SupabaseIncidentStore())

    try:
        await start_test_incident(service_name="payments-api", tenant_id="tenant-123")

        assert fake_db.upsert_processing_incident.await_count == 1
        assert (
            fake_db.upsert_processing_incident.await_args.kwargs["tenant_id"]
            == "tenant-123"
        )
    finally:
        config_module.get_settings.cache_clear()
        supabase_client_module.is_supabase_db_enabled.cache_clear()


@pytest.mark.anyio
async def test_process_uses_fallback_context_and_never_fails_incident(monkeypatch):
    import src.onboarding.test_incident as test_incident_module
    from src.models import PagerDutyIncident, Severity

    class _FakeOrchestrator:
        def __init__(self, _settings):
            pass

        async def process_incident(self, incident, slack_channel=None, tenant_id=None):
            raise RuntimeError("fallback path boom")

    complete_mock = AsyncMock()
    fail_mock = AsyncMock()

    monkeypatch.setattr(test_incident_module, "ContextOrchestrator", _FakeOrchestrator)
    monkeypatch.setattr(
        test_incident_module.incident_store, "complete_incident", complete_mock
    )
    monkeypatch.setattr(test_incident_module.incident_store, "fail_incident", fail_mock)

    incident = PagerDutyIncident(
        incident_id="inc-fallback",
        title="Fallback test",
        description="test",
        severity=Severity.HIGH,
        service_name="payments-api",
        triggered_at=datetime.now(UTC),
        html_url="https://example.com/inc-fallback",
    )

    await test_incident_module._process(incident, None, "tenant-1")

    complete_mock.assert_awaited_once()
    args = complete_mock.await_args.args
    kwargs = complete_mock.await_args.kwargs
    fallback_card = args[1]
    assert fallback_card.incident_id == "inc-fallback"
    assert fallback_card.ai_summary is not None
    assert fallback_card.errors
    assert "orchestrator" in fallback_card.errors[0]
    assert kwargs["metadata"]["fallback"] is True
    assert "fallback path boom" in kwargs["metadata"]["error"]
    fail_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_passes_tenant_id_to_orchestrator(monkeypatch):
    """Verify _process forwards tenant_id to orchestrator.process_incident."""
    import src.onboarding.test_incident as test_incident_module
    from src.models import PagerDutyIncident, Severity

    captured = {}

    class _CapturingOrchestrator:
        def __init__(self, _settings):
            pass

        async def process_incident(self, incident, slack_channel=None, tenant_id=None):
            captured["tenant_id"] = tenant_id
            return ContextCard(
                incident_id=incident.incident_id,
                title=incident.title,
                severity=incident.severity,
                service_name=incident.service_name,
                triggered_at=incident.triggered_at,
                alert_url="https://example.com",
                assembly_time_ms=0,
            )

    monkeypatch.setattr(
        test_incident_module, "ContextOrchestrator", _CapturingOrchestrator
    )
    monkeypatch.setattr(
        test_incident_module.incident_store, "complete_incident", AsyncMock()
    )

    incident = PagerDutyIncident(
        incident_id="inc-tenant-test",
        title="Tenant forwarding test",
        description="test",
        severity=Severity.HIGH,
        service_name="payments-api",
        triggered_at=datetime.now(UTC),
        html_url="https://example.com/inc-tenant-test",
    )

    await test_incident_module._process(incident, None, "tenant-abc-123")

    assert captured["tenant_id"] == "tenant-abc-123"
