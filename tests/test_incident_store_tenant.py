"""Tests for tenant-scoped incident store filtering."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.models import Severity
from src.web.store import HybridIncidentStore, InMemoryIncidentStore


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
async def test_hybrid_store_repairs_memory_tenant_visibility():
    store = HybridIncidentStore()
    store._supabase.add_incident = AsyncMock(return_value=None)
    store._memory._tenant_map = {}

    await store.add_incident(
        incident_id="inc-hybrid-tenant-fix",
        title="Hybrid tenant repair",
        service_name="payments-api",
        severity=Severity.HIGH,
        triggered_at=datetime.now(timezone.utc),
        tenant_id="tenant-a",
    )

    incident = await store.get_incident("inc-hybrid-tenant-fix", tenant_id="tenant-a")

    assert incident is not None
