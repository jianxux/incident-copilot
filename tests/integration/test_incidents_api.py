"""Integration tests for frontend-facing incidents REST API."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import Severity
from src.web.store import incident_store

TEST_TENANT_ID = "tenant-incidents"


@pytest.fixture(scope="module")
def app():
    from src.main import create_app

    return create_app()


@pytest.fixture(scope="module")
def authed_client(app):
    from fastapi.testclient import TestClient

    from src.auth.middleware import AuthContext, get_auth_context

    mock_tenant = MagicMock()
    mock_tenant.id = TEST_TENANT_ID
    mock_tenant.slug = TEST_TENANT_ID

    mock_user = MagicMock()
    mock_user.id = "user-incidents"
    mock_user.email = "oncall@example.com"

    async def override_auth():
        return AuthContext(user=mock_user, tenant=mock_tenant)

    app.dependency_overrides[get_auth_context] = override_auth

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def anon_client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        yield client


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture(autouse=True)
def _force_inmemory_listing(monkeypatch):
    from src.api import incidents as incidents_api

    # Avoid Supabase queries in integration tests; validate API contract against
    # the in-process incident store instead.
    monkeypatch.setattr(incidents_api, "is_supabase_db_enabled", lambda: False)


@pytest.fixture(autouse=True)
def _reset_incident_state():
    from src.api import incidents as incidents_api

    incidents_api._IN_MEMORY_NOTES.clear()
    incidents_api._IN_MEMORY_TIMELINE.clear()

    if hasattr(incident_store, "_incidents"):
        incident_store._incidents.clear()
    if hasattr(incident_store, "_order"):
        incident_store._order.clear()
    if hasattr(incident_store, "_subscribers"):
        incident_store._subscribers.clear()
    if hasattr(incident_store, "_tenant_map"):
        incident_store._tenant_map.clear()
    if hasattr(incident_store, "_memory"):
        if hasattr(incident_store._memory, "_incidents"):
            incident_store._memory._incidents.clear()
        if hasattr(incident_store._memory, "_order"):
            incident_store._memory._order.clear()
        if hasattr(incident_store._memory, "_subscribers"):
            incident_store._memory._subscribers.clear()
        if hasattr(incident_store._memory, "_tenant_map"):
            incident_store._memory._tenant_map.clear()

    now = datetime.now(UTC)
    _run(
        incident_store.add_incident(
            incident_id="inc-1001",
            title="API latency spike",
            service_name="api",
            severity=Severity.HIGH,
            triggered_at=now - timedelta(hours=4),
            tenant_id=TEST_TENANT_ID,
        )
    )
    _run(
        incident_store.add_incident(
            incident_id="inc-1002",
            title="Database saturation",
            service_name="api",
            severity=Severity.CRITICAL,
            triggered_at=now - timedelta(hours=3),
            tenant_id=TEST_TENANT_ID,
        )
    )
    _run(
        incident_store.add_incident(
            incident_id="inc-1003",
            title="Billing queue delay",
            service_name="billing",
            severity=Severity.MEDIUM,
            triggered_at=now - timedelta(hours=2),
            tenant_id=TEST_TENANT_ID,
        )
    )
    _run(
        incident_store.add_incident(
            incident_id="inc-1004",
            title="Worker crash loop",
            service_name="workers",
            severity=Severity.LOW,
            triggered_at=now - timedelta(hours=1),
            tenant_id=TEST_TENANT_ID,
        )
    )

    inc2 = _run(incident_store.get_incident("inc-1002"))
    inc2.status = "acknowledged"

    inc3 = _run(incident_store.get_incident("inc-1003"))
    inc3.status = "completed"
    inc3.processed_at = now - timedelta(hours=1, minutes=20)

    inc4 = _run(incident_store.get_incident("inc-1004"))
    inc4.status = "error"


def test_list_response_matches_frontend_contract(authed_client):
    response = authed_client.get("/api/incidents", params={"page": 1, "limit": 2})
    assert response.status_code == 200

    payload = response.json()
    assert set(payload.keys()) == {"incidents", "total"}
    assert isinstance(payload["incidents"], list)
    assert payload["total"] >= 3
    assert len(payload["incidents"]) == 2

    incident = payload["incidents"][0]
    required_fields = {
        "id",
        "title",
        "severity",
        "status",
        "source",
        "service",
        "created_at",
        "updated_at",
    }
    assert required_fields.issubset(set(incident.keys()))

    filtered = authed_client.get("/api/incidents", params={"service": "api", "limit": 10})
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert filtered_payload["total"] == 2
    assert all(item["service"] == "api" for item in filtered_payload["incidents"])


def test_list_endpoint_awaits_pd_sync_trigger(authed_client):
    with patch("src.api.incidents._trigger_pd_sync_best_effort", new_callable=AsyncMock) as mock_sync:
        response = authed_client.get("/api/incidents")

    assert response.status_code == 200
    mock_sync.assert_awaited_once_with("tenant-incidents")


def test_stats_response_matches_frontend_contract(authed_client):
    response = authed_client.get("/api/incidents/stats")
    assert response.status_code == 200

    payload = response.json()
    assert payload["total"] >= 4
    assert set(payload["by_status"].keys()) == {
        "triggered",
        "acknowledged",
        "resolved",
        "processing",
    }
    assert payload["by_status"]["processing"] == 2
    assert set(payload["by_severity"].keys()) == {
        "critical",
        "high",
        "medium",
        "low",
        "info",
    }
    assert isinstance(payload["mttr_hours"], float)
    assert isinstance(payload["mtta_minutes"], float)
    assert isinstance(payload["incidents_today"], int)
    assert isinstance(payload["incidents_week"], int)


def test_get_acknowledge_and_resolve_incident(authed_client):
    detail = authed_client.get("/api/incidents/inc-1001")
    assert detail.status_code == 200
    assert detail.json()["id"] == "inc-1001"

    ack = authed_client.post("/api/incidents/inc-1001/acknowledge")
    assert ack.status_code == 200
    ack_payload = ack.json()
    assert ack_payload["status"] == "acknowledged"
    assert ack_payload["acknowledged_at"]

    resolve = authed_client.post(
        "/api/incidents/inc-1001/resolve",
        json={"resolution": "Rolled back deployment"},
    )
    assert resolve.status_code == 200
    resolved_payload = resolve.json()
    assert resolved_payload["status"] == "resolved"
    assert resolved_payload["resolved_at"]


def test_context_timeline_notes_and_similar(authed_client):
    context_response = authed_client.get("/api/incidents/inc-1001/context")
    assert context_response.status_code == 200
    context_payload = context_response.json()
    assert context_payload["incident_id"] == "inc-1001"

    note_response = authed_client.post(
        "/api/incidents/inc-1001/notes",
        json={"content": "Investigating recent deploy"},
    )
    assert note_response.status_code == 200
    note_payload = note_response.json()
    assert note_payload["incident_id"] == "inc-1001"
    assert note_payload["content"] == "Investigating recent deploy"

    timeline_response = authed_client.get("/api/incidents/inc-1001/timeline")
    assert timeline_response.status_code == 200
    timeline_payload = timeline_response.json()
    assert isinstance(timeline_payload, list)
    assert any(event["type"] == "comment" for event in timeline_payload)
    assert any("timestamp" in event for event in timeline_payload)

    similar_response = authed_client.get("/api/incidents/inc-1001/similar")
    assert similar_response.status_code == 200
    similar_payload = similar_response.json()
    assert isinstance(similar_payload, list)
    if similar_payload:
        assert {"id", "title", "severity", "status"}.issubset(set(similar_payload[0].keys()))


def test_incident_list_endpoint_requires_auth():
    """Unauthenticated GET /api/incidents requests return auth_required."""
    from fastapi.testclient import TestClient

    from src.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/incidents")

    assert response.status_code == 401
    assert response.json() == {"detail": "auth_required"}
