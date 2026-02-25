"""Tests for PagerDuty/Opsgenie provenance data sync."""

from datetime import UTC, datetime

import pytest

from src.integrations.pagerduty_sync import _build_pd_upsert_rows
from src.models import ContextCard, Severity
from src.web.store import InMemoryIncidentStore


@pytest.fixture
def store():
    return InMemoryIncidentStore(max_incidents=50)


@pytest.mark.asyncio
async def test_store_accepts_provenance_fields(store):
    """add_incident persists source, source_url, source_id, and metadata."""
    incident = await store.add_incident(
        incident_id="PD-001",
        title="High CPU on payments-api",
        service_name="payments-api",
        severity=Severity.HIGH,
        triggered_at=datetime.now(UTC),
        source="pagerduty",
        source_url="https://acme.pagerduty.com/incidents/PD-001",
        source_id="PD-001",
        metadata={"provider": "pagerduty"},
    )

    assert incident.source == "pagerduty"
    assert incident.source_url == "https://acme.pagerduty.com/incidents/PD-001"
    assert incident.source_id == "PD-001"
    assert incident.metadata == {"provider": "pagerduty"}


@pytest.mark.asyncio
async def test_provenance_in_api_response(store):
    """Provenance fields are retrievable after storage."""
    await store.add_incident(
        incident_id="OG-100",
        title="Latency spike",
        service_name="checkout-api",
        severity=Severity.MEDIUM,
        triggered_at=datetime.now(UTC),
        source="opsgenie",
        source_url="https://app.opsgenie.com/alert/OG-100",
        source_id="OG-100",
        metadata={"provider": "opsgenie"},
    )

    fetched = await store.get_incident("OG-100")
    assert fetched is not None
    assert fetched.source == "opsgenie"
    assert fetched.source_url == "https://app.opsgenie.com/alert/OG-100"
    assert fetched.source_id == "OG-100"

    all_incidents = await store.get_all_incidents()
    match = [i for i in all_incidents if i.incident_id == "OG-100"]
    assert len(match) == 1
    assert match[0].source == "opsgenie"


@pytest.mark.asyncio
async def test_complete_incident_merges_metadata(store):
    """complete_incident merges new metadata with existing provenance metadata."""
    await store.add_incident(
        incident_id="PD-002",
        title="DB connection pool exhausted",
        service_name="user-service",
        severity=Severity.CRITICAL,
        triggered_at=datetime.now(UTC),
        source="pagerduty",
        source_url="https://acme.pagerduty.com/incidents/PD-002",
        source_id="PD-002",
        metadata={"provider": "pagerduty"},
    )

    card = ContextCard(
        incident_id="PD-002",
        title="DB connection pool exhausted",
        severity=Severity.CRITICAL,
        service_name="user-service",
        triggered_at=datetime.now(UTC),
        assembled_at=datetime.now(UTC),
        assembly_time_ms=1200,
    )

    result = await store.complete_incident(
        "PD-002", card, metadata={"verdict": "connection leak"}
    )

    assert result is not None
    assert result.status == "completed"
    assert result.metadata["provider"] == "pagerduty"
    assert result.metadata["verdict"] == "connection leak"
    assert result.source == "pagerduty"


@pytest.mark.asyncio
async def test_default_provenance_when_omitted(store):
    """Omitting provenance fields falls back to defaults."""
    incident = await store.add_incident(
        incident_id="MANUAL-1",
        title="Manual incident",
        service_name="test-svc",
        severity=Severity.LOW,
        triggered_at=datetime.now(UTC),
    )

    assert incident.source == "manual"
    assert incident.source_url is None
    assert incident.source_id == "MANUAL-1"
    assert incident.metadata == {}


def test_build_pd_upsert_rows_includes_description():
    rows, _ = _build_pd_upsert_rows(
        [
            {
                "id": "PD-DESC-1",
                "title": "Disk usage high",
                "description": "Root volume above 90%",
                "created_at": "2026-02-20T10:00:00Z",
                "status": "triggered",
            }
        ],
        tenant_id="tenant-1",
    )

    assert len(rows) == 1
    assert rows[0]["description"] == "Root volume above 90%"


def test_build_pd_upsert_rows_sets_acknowledged_at_metadata():
    rows, _ = _build_pd_upsert_rows(
        [
            {
                "id": "PD-ACK-1",
                "title": "API latency spike",
                "created_at": "2026-02-20T10:00:00Z",
                "status": "acknowledged",
                "last_status_change_at": "2026-02-20T11:22:33Z",
            }
        ],
        tenant_id="tenant-1",
    )

    assert len(rows) == 1
    metadata = rows[0]["metadata"]
    assert metadata["acknowledged_at"] == "2026-02-20T11:22:33+00:00"
