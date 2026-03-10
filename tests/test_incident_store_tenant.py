"""Tests for tenant visibility rules in the in-memory incident store."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.models import Severity
from src.web.store import HybridIncidentStore, InMemoryIncidentStore


@pytest.mark.asyncio
async def test_unscoped_incidents_are_visible_with_tenant_filter():
    store = InMemoryIncidentStore()

    await store.add_incident(
        incident_id="inc-unscoped",
        title="Unscoped incident",
        service_name="core-api",
        severity=Severity.MEDIUM,
        triggered_at=datetime.now(timezone.utc),
    )
    await store.add_incident(
        incident_id="inc-tenant-a",
        title="Tenant A incident",
        service_name="payments-api",
        severity=Severity.HIGH,
        triggered_at=datetime.now(timezone.utc),
        tenant_id="tenant-a",
    )

    tenant_a_incidents = await store.get_all_incidents(tenant_id="tenant-a")

    assert {inc.incident_id for inc in tenant_a_incidents} == {
        "inc-unscoped",
        "inc-tenant-a",
    }

@pytest.mark.asyncio
async def test_scoped_incidents_are_only_visible_to_their_tenant():
    store = InMemoryIncidentStore()

    await store.add_incident(
        incident_id="inc-tenant-a",
        title="Tenant A incident",
        service_name="api",
        severity=Severity.HIGH,
        triggered_at=datetime.now(timezone.utc),
        tenant_id="tenant-a",
    )
    await store.add_incident(
        incident_id="inc-tenant-b",
        title="Tenant B incident",
        service_name="api",
        severity=Severity.LOW,
        triggered_at=datetime.now(timezone.utc),
        tenant_id="tenant-b",
    )

    tenant_a_incidents = await store.get_all_incidents(tenant_id="tenant-a")
    tenant_b_incidents = await store.get_all_incidents(tenant_id="tenant-b")

    assert {inc.incident_id for inc in tenant_a_incidents} == {"inc-tenant-a"}
    assert {inc.incident_id for inc in tenant_b_incidents} == {"inc-tenant-b"}


@pytest.mark.asyncio
async def test_get_incident_returns_unscoped_for_any_tenant():
    store = InMemoryIncidentStore()

    await store.add_incident(
        incident_id="inc-unscoped",
        title="Unscoped incident",
        service_name="api",
        severity=Severity.HIGH,
        triggered_at=datetime.now(timezone.utc),
    )

    assert (await store.get_incident("inc-unscoped", tenant_id="tenant-a")) is not None
    assert (await store.get_incident("inc-unscoped", tenant_id="tenant-b")) is not None
    assert (await store.get_incident("inc-unscoped", tenant_id=None)) is not None


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
