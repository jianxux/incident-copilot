from __future__ import annotations

from unittest.mock import AsyncMock

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
    monkeypatch.setattr(
        test_incident_module, "incident_store", SupabaseIncidentStore()
    )

    await start_test_incident(service_name="payments-api", tenant_id="tenant-123")

    assert fake_db.upsert_processing_incident.await_count == 1
    assert (
        fake_db.upsert_processing_incident.await_args.kwargs["tenant_id"]
        == "tenant-123"
    )
