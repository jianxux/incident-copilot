"""Tests for HybridIncidentStore persistence and error handling."""

from datetime import UTC, datetime

import pytest

from src.models import Severity
from src.web.store import InMemoryIncidentStore


@pytest.fixture
def store():
    return InMemoryIncidentStore(max_incidents=50)


@pytest.mark.asyncio
async def test_tenant_id_cached_on_add(store):
    """When tenant_id is passed to add_incident, subsequent get uses it."""
    await store.add_incident(
        incident_id="INC-001",
        title="Test incident",
        service_name="api",
        severity=Severity.HIGH,
        triggered_at=datetime.now(UTC),
        tenant_id="tenant-abc",
    )

    # Should find with correct tenant
    found = await store.get_incident("INC-001", tenant_id="tenant-abc")
    assert found is not None
    assert found.incident_id == "INC-001"

    # Should NOT find with wrong tenant
    not_found = await store.get_incident("INC-001", tenant_id="tenant-xyz")
    assert not_found is None


@pytest.mark.asyncio
async def test_tenant_scoped_list(store):
    """get_all_incidents filters by tenant_id."""
    await store.add_incident(
        incident_id="INC-A",
        title="Tenant A incident",
        service_name="api",
        severity=Severity.HIGH,
        triggered_at=datetime.now(UTC),
        tenant_id="tenant-a",
    )
    await store.add_incident(
        incident_id="INC-B",
        title="Tenant B incident",
        service_name="api",
        severity=Severity.MEDIUM,
        triggered_at=datetime.now(UTC),
        tenant_id="tenant-b",
    )

    a_incidents = await store.get_all_incidents(tenant_id="tenant-a")
    assert len(a_incidents) == 1
    assert a_incidents[0].incident_id == "INC-A"

    all_incidents = await store.get_all_incidents(tenant_id=None)
    assert len(all_incidents) == 2


@pytest.mark.asyncio
async def test_unscoped_incident_visible_without_tenant(store):
    """Incidents added without tenant_id are visible when listing without tenant filter."""
    await store.add_incident(
        incident_id="INC-UNSCOPED",
        title="Unscoped incident",
        service_name="api",
        severity=Severity.LOW,
        triggered_at=datetime.now(UTC),
    )

    all_incidents = await store.get_all_incidents()
    assert len(all_incidents) == 1

    # Unscoped incidents are NOT visible when filtering by a specific tenant
    tenant_incidents = await store.get_all_incidents(tenant_id="some-tenant")
    assert len(tenant_incidents) == 0
