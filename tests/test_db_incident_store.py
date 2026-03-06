"""Tests for DatabaseIncidentStore and InMemoryIncidentStore."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

os.environ["SUPABASE_DB_ENABLED"] = "false"
os.environ.pop("SUPABASE_URL", None)

from src.models import ContextCard, Severity
from src.web.store import InMemoryIncidentStore, DatabaseIncidentStore


# ---------------------------------------------------------------------------
# InMemoryIncidentStore tests
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_store():
    return InMemoryIncidentStore(max_incidents=5)


@pytest.mark.anyio
async def test_add_and_get_incident(memory_store):
    now = datetime.now(UTC)
    result = await memory_store.add_incident(
        incident_id="INC-001",
        title="CPU spike",
        service_name="payments-api",
        severity=Severity.HIGH,
        triggered_at=now,
    )
    assert result.incident_id == "INC-001"
    assert result.status == "processing"

    fetched = await memory_store.get_incident("INC-001")
    assert fetched is not None
    assert fetched.title == "CPU spike"


@pytest.mark.anyio
async def test_complete_incident(memory_store):
    now = datetime.now(UTC)
    await memory_store.add_incident(
        incident_id="INC-002",
        title="Disk full",
        service_name="storage-svc",
        severity=Severity.CRITICAL,
        triggered_at=now,
    )
    card = ContextCard(
        incident_id="INC-002",
        title="Disk full",
        severity=Severity.CRITICAL,
        service_name="storage-svc",
        triggered_at=now,
        assembly_time_ms=150,
    )
    result = await memory_store.complete_incident("INC-002", card)
    assert result is not None
    assert result.status == "completed"
    assert result.context_card is not None


@pytest.mark.anyio
async def test_fail_incident(memory_store):
    now = datetime.now(UTC)
    await memory_store.add_incident(
        incident_id="INC-003",
        title="Timeout",
        service_name="api-gw",
        severity=Severity.MEDIUM,
        triggered_at=now,
    )
    result = await memory_store.fail_incident("INC-003", "connection refused")
    assert result is not None
    assert result.status == "error"
    assert result.error_message == "connection refused"


@pytest.mark.anyio
async def test_get_all_incidents_order(memory_store):
    for i in range(3):
        await memory_store.add_incident(
            incident_id=f"INC-{i}",
            title=f"Incident {i}",
            service_name="svc",
            severity=Severity.LOW,
            triggered_at=datetime.now(UTC),
        )
    all_incidents = await memory_store.get_all_incidents()
    assert len(all_incidents) == 3
    # Newest first
    assert all_incidents[0].incident_id == "INC-2"


@pytest.mark.anyio
async def test_max_incidents_trimming(memory_store):
    for i in range(7):
        await memory_store.add_incident(
            incident_id=f"INC-{i}",
            title=f"Incident {i}",
            service_name="svc",
            severity=Severity.LOW,
            triggered_at=datetime.now(UTC),
        )
    all_incidents = await memory_store.get_all_incidents()
    assert len(all_incidents) == 5  # max_incidents=5


@pytest.mark.anyio
async def test_get_stats(memory_store):
    now = datetime.now(UTC)
    await memory_store.add_incident("INC-A", "A", "svc", Severity.HIGH, now)
    await memory_store.add_incident("INC-B", "B", "svc", Severity.LOW, now)
    await memory_store.fail_incident("INC-B", "boom")

    stats = await memory_store.get_stats()
    assert stats["total"] == 2
    assert stats["by_status"]["processing"] == 1
    assert stats["by_status"]["error"] == 1


@pytest.mark.anyio
async def test_nonexistent_incident(memory_store):
    result = await memory_store.get_incident("NOPE")
    assert result is None

    result = await memory_store.complete_incident(
        "NOPE",
        ContextCard(
            incident_id="NOPE",
            title="x",
            severity=Severity.LOW,
            service_name="x",
            triggered_at=datetime.now(UTC),
        ),
    )
    assert result is None


# ---------------------------------------------------------------------------
# DatabaseIncidentStore model tests (no real DB needed)
# ---------------------------------------------------------------------------


def test_incident_row_model():
    """Verify the SQLAlchemy model can be imported and has expected columns."""
    from src.web.models import IncidentRow, Base

    assert "incidents" == IncidentRow.__tablename__
    col_names = {c.name for c in IncidentRow.__table__.columns}
    expected = {
        "incident_id",
        "title",
        "service_name",
        "severity",
        "status",
        "triggered_at",
        "processed_at",
        "context_card",
        "error_message",
    }
    assert expected.issubset(col_names)


def test_init_db_function_exists():
    from src.web.models import init_db
    import inspect

    assert inspect.iscoroutinefunction(init_db)
