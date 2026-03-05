"""Tests for incident store persistence and tenant_id propagation."""

from datetime import UTC, datetime

import pytest

from src.models import Severity
from src.web.store import InMemoryIncidentStore, SupabaseIncidentStore


@pytest.fixture
def memory_store():
    return InMemoryIncidentStore(max_incidents=50)


@pytest.mark.asyncio
async def test_tenant_id_cached_across_add_and_complete(memory_store):
    """Verify tenant_id set in add_incident is retrievable in get_all_incidents."""
    tenant = "tenant-abc-123"

    await memory_store.add_incident(
        incident_id="INC-001",
        title="Test persistence",
        service_name="api-gateway",
        severity=Severity.HIGH,
        triggered_at=datetime.now(UTC),
        tenant_id=tenant,
    )

    # Should be visible with correct tenant
    incidents = await memory_store.get_all_incidents(tenant_id=tenant)
    assert len(incidents) == 1
    assert incidents[0].incident_id == "INC-001"

    # Should NOT be visible with wrong tenant
    incidents = await memory_store.get_all_incidents(tenant_id="wrong-tenant")
    assert len(incidents) == 0


@pytest.mark.asyncio
async def test_supabase_store_caches_tenant_in_resolve():
    """SupabaseIncidentStore._resolve_tenant caches tenant_id from add calls."""
    store = SupabaseIncidentStore(max_incidents=50)

    # Simulate caching by calling _resolve_tenant with explicit tenant_id
    resolved = await store._resolve_tenant(
        incident_id="INC-002",
        tenant_id="tenant-xyz",
    )
    assert resolved == "tenant-xyz"

    # Now resolving without tenant_id should use cached value
    resolved = await store._resolve_tenant(incident_id="INC-002")
    assert resolved == "tenant-xyz"


@pytest.mark.asyncio
async def test_incident_survives_complete_cycle(memory_store):
    """Incident added then completed should be retrievable."""
    from src.models import AILogSummary, ContextCard

    tenant = "tenant-test"
    now = datetime.now(UTC)

    await memory_store.add_incident(
        incident_id="INC-003",
        title="Completion test",
        service_name="checkout",
        severity=Severity.CRITICAL,
        triggered_at=now,
        tenant_id=tenant,
    )

    card = ContextCard(
        incident_id="INC-003",
        title="Completion test",
        severity=Severity.CRITICAL,
        service_name="checkout",
        triggered_at=now,
        assembly_time_ms=150,
    )

    result = await memory_store.complete_incident(
        "INC-003", card, tenant_id=tenant,
    )
    assert result is not None
    assert result.status == "completed"

    # Should still be visible
    incidents = await memory_store.get_all_incidents(tenant_id=tenant)
    assert len(incidents) == 1
    assert incidents[0].status == "completed"
