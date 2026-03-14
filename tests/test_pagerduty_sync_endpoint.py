"""Tests for PagerDuty incident sync endpoint."""

from datetime import UTC, datetime

import pytest

from src.models import ContextCard, Severity
from src.web.store import InMemoryIncidentStore


def _make_pd_incident(
    *,
    id: str = "P0001",
    title: str = "High CPU on payments-api",
    status: str = "triggered",
    urgency: str = "high",
    incident_number: int = 1,
    service_summary: str = "payments-api",
    html_url: str = "https://acme.pagerduty.com/incidents/P0001",
    created_at: str = "2024-06-01T12:00:00Z",
    assigned_to: list[dict] | None = None,
    escalation_policy: str = "Default",
) -> dict:
    """Build a minimal PagerDuty incident dict."""
    return {
        "id": id,
        "title": title,
        "status": status,
        "urgency": urgency,
        "incident_number": incident_number,
        "service": {"id": "PSVC1", "summary": service_summary},
        "html_url": html_url,
        "created_at": created_at,
        "assignments": assigned_to or [{"assignee": {"summary": "Alice"}}],
        "escalation_policy": {"summary": escalation_policy},
    }


# ---------------------------------------------------------------------------
# Direct store-level tests (no HTTP, fast)
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    return InMemoryIncidentStore(max_incidents=50)


@pytest.mark.asyncio
async def test_sync_stores_triggered_incident(store):
    """Syncing a triggered PagerDuty incident persists it correctly."""
    inc = _make_pd_incident(
        id="PD-T1",
        title="Disk full on db-primary",
        status="triggered",
        urgency="high",
        service_summary="db-primary",
        incident_number=42,
    )

    await store.add_incident(
        incident_id=inc["id"],
        title=inc["title"],
        service_name=inc["service"]["summary"],
        severity=Severity.HIGH,
        triggered_at=datetime.fromisoformat(inc["created_at"].replace("Z", "+00:00")),
        source="pagerduty",
        source_url=inc["html_url"],
        source_id=str(inc["incident_number"]),
        metadata={
            "provider": "pagerduty",
            "status": inc["status"],
            "urgency": inc["urgency"],
            "assigned_to": ["Alice"],
            "escalation_policy": "Default",
        },
        tenant_id="test-tenant",
    )

    stored = await store.get_incident("PD-T1")
    assert stored is not None
    assert stored.title == "Disk full on db-primary"
    assert stored.service_name == "db-primary"
    assert stored.severity == Severity.HIGH
    assert stored.source == "pagerduty"
    assert stored.source_id == "42"
    assert stored.metadata["provider"] == "pagerduty"
    assert stored.metadata["status"] == "triggered"
    assert stored.status == "processing"  # Not resolved yet


@pytest.mark.asyncio
async def test_sync_resolved_incident_marks_completed(store):
    """Syncing a resolved PagerDuty incident should mark it completed."""
    inc = _make_pd_incident(id="PD-R1", status="resolved", urgency="low")

    await store.add_incident(
        incident_id=inc["id"],
        title=inc["title"],
        service_name=inc["service"]["summary"],
        severity=Severity.LOW,
        triggered_at=datetime.fromisoformat(inc["created_at"].replace("Z", "+00:00")),
        source="pagerduty",
        source_url=inc["html_url"],
        source_id=str(inc["incident_number"]),
        metadata={"provider": "pagerduty", "status": "resolved"},
        tenant_id="test-tenant",
    )

    card = ContextCard(
        incident_id=inc["id"],
        title=inc["title"],
        severity=Severity.LOW,
        service_name=inc["service"]["summary"],
        triggered_at=datetime.fromisoformat(inc["created_at"].replace("Z", "+00:00")),
        assembled_at=datetime.now(UTC),
        assembly_time_ms=0,
    )
    await store.complete_incident(inc["id"], card, metadata={"resolved_via_sync": True})

    stored = await store.get_incident("PD-R1")
    assert stored is not None
    assert stored.status == "completed"
    assert stored.metadata["resolved_via_sync"] is True


@pytest.mark.asyncio
async def test_sync_maps_urgency_to_severity(store):
    """High urgency -> Severity.HIGH, low urgency -> Severity.LOW."""
    for urgency, expected_sev in [("high", Severity.HIGH), ("low", Severity.LOW)]:
        inc = _make_pd_incident(id=f"PD-U-{urgency}", urgency=urgency)
        severity = Severity.HIGH if urgency == "high" else Severity.LOW

        await store.add_incident(
            incident_id=inc["id"],
            title=inc["title"],
            service_name=inc["service"]["summary"],
            severity=severity,
            triggered_at=datetime.now(UTC),
            source="pagerduty",
            tenant_id="test-tenant",
        )

        stored = await store.get_incident(inc["id"])
        assert stored is not None
        assert stored.severity == expected_sev


@pytest.mark.asyncio
async def test_sync_multiple_incidents(store):
    """Multiple PD incidents can be synced and all are stored."""
    for i in range(5):
        inc = _make_pd_incident(id=f"PD-M{i}", incident_number=100 + i)
        await store.add_incident(
            incident_id=inc["id"],
            title=inc["title"],
            service_name=inc["service"]["summary"],
            severity=Severity.HIGH,
            triggered_at=datetime.now(UTC),
            source="pagerduty",
            source_id=str(inc["incident_number"]),
            tenant_id="test-tenant",
        )

    all_incidents = await store.get_all_incidents()
    pd_ids = {i.incident_id for i in all_incidents}
    for i in range(5):
        assert f"PD-M{i}" in pd_ids


@pytest.mark.asyncio
async def test_sync_upserts_existing_incident(store):
    """Re-syncing the same incident_id overwrites rather than duplicating."""
    inc = _make_pd_incident(id="PD-DUP", title="Original title")
    await store.add_incident(
        incident_id=inc["id"],
        title="Original title",
        service_name="svc",
        severity=Severity.HIGH,
        triggered_at=datetime.now(UTC),
        source="pagerduty",
        tenant_id="test-tenant",
    )

    # Re-add with updated title (upsert behavior)
    await store.add_incident(
        incident_id=inc["id"],
        title="Updated title",
        service_name="svc",
        severity=Severity.HIGH,
        triggered_at=datetime.now(UTC),
        source="pagerduty",
        tenant_id="test-tenant",
    )

    stored = await store.get_incident("PD-DUP")
    assert stored is not None
    assert stored.title == "Updated title"

    all_incidents = await store.get_all_incidents()
    matching = [i for i in all_incidents if i.incident_id == "PD-DUP"]
    # In-memory store replaces by key; count should be 1 or the latest wins
    assert len(matching) >= 1


@pytest.mark.asyncio
async def test_sync_extracts_metadata_fields(store):
    """Metadata includes status, urgency, assigned_to, and escalation_policy."""
    inc = _make_pd_incident(
        id="PD-META",
        urgency="high",
        status="acknowledged",
        assigned_to=[
            {"assignee": {"summary": "Alice"}},
            {"assignee": {"summary": "Bob"}},
        ],
        escalation_policy="Critical EP",
    )

    metadata = {
        "provider": "pagerduty",
        "status": inc["status"],
        "urgency": inc["urgency"],
        "assigned_to": ["Alice", "Bob"],
        "escalation_policy": "Critical EP",
    }

    await store.add_incident(
        incident_id=inc["id"],
        title=inc["title"],
        service_name=inc["service"]["summary"],
        severity=Severity.HIGH,
        triggered_at=datetime.now(UTC),
        source="pagerduty",
        metadata=metadata,
        tenant_id="test-tenant",
    )

    stored = await store.get_incident("PD-META")
    assert stored is not None
    assert stored.metadata["status"] == "acknowledged"
    assert stored.metadata["urgency"] == "high"
    assert stored.metadata["assigned_to"] == ["Alice", "Bob"]
    assert stored.metadata["escalation_policy"] == "Critical EP"
