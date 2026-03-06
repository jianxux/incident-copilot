"""Tests for tenant-scoped incident store filtering."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.models import Severity
from src.web.store import HybridIncidentStore, InMemoryIncidentStore, SupabaseIncidentStore


@pytest.mark.asyncio
async def test_inmemory_store_filters_by_tenant():
    store = InMemoryIncidentStore()

    await store.add_incident(
        incident_id="inc-tenant-a-1",
        title="Tenant A incident 1",
        service_name="payments-api",
        severity=Severity.HIGH,
        triggered_at=datetime.now(timezone.utc),
        tenant_id="tenant-a",
    )
    await store.add_incident(
        incident_id="inc-tenant-b-1",
        title="Tenant B incident",
        service_name="orders-api",
        severity=Severity.MEDIUM,
        triggered_at=datetime.now(timezone.utc),
        tenant_id="tenant-b",
    )
    await store.add_incident(
        incident_id="inc-tenant-a-2",
        title="Tenant A incident 2",
        service_name="checkout-api",
        severity=Severity.LOW,
        triggered_at=datetime.now(timezone.utc),
        tenant_id="tenant-a",
    )

    tenant_a_incidents = await store.get_all_incidents(tenant_id="tenant-a")

    assert {inc.incident_id for inc in tenant_a_incidents} == {
        "inc-tenant-a-1",
        "inc-tenant-a-2",
    }

    tenant_b_incidents = await store.get_all_incidents(tenant_id="tenant-b")
    assert [inc.incident_id for inc in tenant_b_incidents] == ["inc-tenant-b-1"]


@pytest.mark.asyncio
async def test_inmemory_store_returns_all_when_no_tenant():
    store = InMemoryIncidentStore()

    await store.add_incident(
        incident_id="inc-tenant-a",
        title="Tenant A incident",
        service_name="payments-api",
        severity=Severity.HIGH,
        triggered_at=datetime.now(timezone.utc),
        tenant_id="tenant-a",
    )
    await store.add_incident(
        incident_id="inc-no-tenant",
        title="No tenant incident",
        service_name="core-api",
        severity=Severity.MEDIUM,
        triggered_at=datetime.now(timezone.utc),
        tenant_id=None,
    )

    incidents = await store.get_all_incidents(tenant_id=None)

    assert {inc.incident_id for inc in incidents} == {
        "inc-tenant-a",
        "inc-no-tenant",
    }


@pytest.mark.asyncio
async def test_inmemory_store_get_incident_filters_tenant():
    store = InMemoryIncidentStore()

    await store.add_incident(
        incident_id="inc-1",
        title="Tenant A incident",
        service_name="api",
        severity=Severity.HIGH,
        triggered_at=datetime.now(timezone.utc),
        tenant_id="tenant-a",
    )

    # Same tenant finds it
    assert (await store.get_incident("inc-1", tenant_id="tenant-a")) is not None
    # Different tenant doesn't
    assert (await store.get_incident("inc-1", tenant_id="tenant-b")) is None
    # No tenant filter finds it
    assert (await store.get_incident("inc-1", tenant_id=None)) is not None


@pytest.mark.asyncio
async def test_hybrid_store_memory_fallback():
    """When Supabase fails, HybridStore falls back to in-memory with tenant filtering."""
    store = HybridIncidentStore()
    store._supabase.add_incident = AsyncMock(return_value=None)
    store._supabase.get_all_incidents = AsyncMock(
        side_effect=RuntimeError("supabase unavailable")
    )

    await store.add_incident(
        incident_id="inc-hybrid-a",
        title="Hybrid tenant A",
        service_name="payments-api",
        severity=Severity.HIGH,
        triggered_at=datetime.now(timezone.utc),
        tenant_id="tenant-a",
    )
    await store.add_incident(
        incident_id="inc-hybrid-b",
        title="Hybrid tenant B",
        service_name="orders-api",
        severity=Severity.MEDIUM,
        triggered_at=datetime.now(timezone.utc),
        tenant_id="tenant-b",
    )

    incidents = await store.get_all_incidents(tenant_id="tenant-a")

    assert [inc.incident_id for inc in incidents] == ["inc-hybrid-a"]


@pytest.mark.asyncio
async def test_hybrid_store_add_incident_raises_on_supabase_failure():
    store = HybridIncidentStore()
    store._supabase.add_incident = AsyncMock(side_effect=RuntimeError("write failed"))

    with pytest.raises(RuntimeError, match="write failed"):
        await store.add_incident(
            incident_id="inc-hybrid-error",
            title="Hybrid error",
            service_name="payments-api",
            severity=Severity.HIGH,
            triggered_at=datetime.now(timezone.utc),
            tenant_id="tenant-a",
        )


@pytest.mark.asyncio
async def test_supabase_store_prefers_explicit_tenant_and_lists_by_tenant(monkeypatch):
    class _FakeDB:
        def __init__(self):
            self.rows_by_tenant: dict[str, dict] = {}

        async def ensure_tenant(self, slug: str, name: str):
            return {"id": "default-tenant"}

        async def upsert_processing_incident(self, **kwargs):
            tenant_id = kwargs["tenant_id"]
            row = {
                "id": kwargs["incident_id"],
                "title": kwargs["title"],
                "service": kwargs["service_name"],
                "severity": kwargs["severity"],
                "status": kwargs["status"],
                "triggered_at": kwargs["triggered_at"],
                "processed_at": kwargs.get("processed_at"),
                "source": kwargs.get("source") or "manual",
                "source_url": kwargs.get("source_url"),
                "source_id": kwargs.get("source_id"),
                "description": kwargs.get("description"),
                "metadata": kwargs.get("metadata") or {},
            }
            self.rows_by_tenant[tenant_id] = row

        async def list_processing_incidents(self, tenant_id: str, limit: int, offset: int):
            row = self.rows_by_tenant.get(tenant_id)
            return [row] if row else []

    import src.db.supabase_db as supabase_db

    fake_db = _FakeDB()
    monkeypatch.setattr(supabase_db, "get_db", lambda use_admin=True: fake_db)

    store = SupabaseIncidentStore()
    store._tenant_id = "default-tenant"
    store._incident_tenants["inc-tenant-explicit"] = "wrong-tenant"

    await store.add_incident(
        incident_id="inc-tenant-explicit",
        title="Tenant explicit incident",
        service_name="payments-api",
        severity=Severity.HIGH,
        triggered_at=datetime.now(timezone.utc),
        tenant_id="tenant-123",
    )

    tenant_incidents = await store.get_all_incidents(tenant_id="tenant-123")
    default_incidents = await store.get_all_incidents(tenant_id="default-tenant")

    assert [inc.incident_id for inc in tenant_incidents] == ["inc-tenant-explicit"]
    assert default_incidents == []
