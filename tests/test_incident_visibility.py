"""Tests for incident visibility across tenant-scoped and unscoped incidents."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.models import Severity
from src.web.store import InMemoryIncidentStore


@pytest.mark.asyncio
async def test_get_all_incidents_includes_unscoped_for_any_tenant():
    store = InMemoryIncidentStore()

    await store.add_incident(
        incident_id="inc-scoped",
        title="Scoped Incident",
        service_name="payments-api",
        severity=Severity.HIGH,
        triggered_at=datetime.now(timezone.utc),
        tenant_id="some-tenant",
    )
    await store.add_incident(
        incident_id="inc-unscoped",
        title="Unscoped Incident",
        service_name="core-api",
        severity=Severity.MEDIUM,
        triggered_at=datetime.now(timezone.utc),
        tenant_id=None,
    )

    some_tenant_incidents = await store.get_all_incidents(tenant_id="some-tenant")
    assert {incident.incident_id for incident in some_tenant_incidents} == {
        "inc-scoped",
        "inc-unscoped",
    }

    other_tenant_incidents = await store.get_all_incidents(tenant_id="other-tenant")
    assert [incident.incident_id for incident in other_tenant_incidents] == ["inc-unscoped"]

    all_incidents = await store.get_all_incidents(tenant_id=None)
    assert {incident.incident_id for incident in all_incidents} == {
        "inc-scoped",
        "inc-unscoped",
    }


@pytest.mark.asyncio
async def test_get_incident_includes_unscoped_for_any_tenant():
    store = InMemoryIncidentStore()

    await store.add_incident(
        incident_id="inc-scoped",
        title="Scoped Incident",
        service_name="payments-api",
        severity=Severity.HIGH,
        triggered_at=datetime.now(timezone.utc),
        tenant_id="some-tenant",
    )
    await store.add_incident(
        incident_id="inc-unscoped",
        title="Unscoped Incident",
        service_name="core-api",
        severity=Severity.MEDIUM,
        triggered_at=datetime.now(timezone.utc),
        tenant_id=None,
    )

    assert (await store.get_incident("inc-scoped", tenant_id="some-tenant")) is not None
    assert (await store.get_incident("inc-scoped", tenant_id="other-tenant")) is None
    assert (await store.get_incident("inc-unscoped", tenant_id="some-tenant")) is not None
    assert (await store.get_incident("inc-unscoped", tenant_id="other-tenant")) is not None
    assert (await store.get_incident("inc-scoped", tenant_id=None)) is not None
    assert (await store.get_incident("inc-unscoped", tenant_id=None)) is not None
