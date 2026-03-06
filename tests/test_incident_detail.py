"""Regression tests for incident detail page rendering and JS guards."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.main import create_app
from src.models import Severity
from src.web.routes.common import require_dashboard_auth
from src.web.store import InMemoryIncidentStore


def _run(coro):
    return asyncio.run(coro)


def _clear_incident_store(store) -> None:
    if hasattr(store, "_incidents"):
        store._incidents.clear()
    if hasattr(store, "_order"):
        store._order.clear()


def _add_processing_incident(
    store,
    *,
    incident_id: str,
    title: str,
    source: str = "pagerduty",
    source_url: str | None = None,
    metadata: dict | None = None,
) -> None:
    _run(
        store.add_incident(
            incident_id=incident_id,
            title=title,
            service_name="payments-api",
            severity=Severity.HIGH,
            triggered_at=datetime.now(UTC),
            source=source,
            source_url=source_url,
            metadata=metadata,
        )
    )


@pytest.fixture
def _in_memory_store(monkeypatch):
    from src.web import store as web_store
    from src.web.routes import pages as pages_routes

    store = InMemoryIncidentStore(max_incidents=100)
    monkeypatch.setattr(web_store, "incident_store", store)
    monkeypatch.setattr(pages_routes, "incident_store", store)
    return store


@pytest.fixture
def client(_in_memory_store):
    async def _allow_dashboard_auth():
        return {"tenant_id": None, "user_id": "test-user"}

    app = create_app()
    app.dependency_overrides[require_dashboard_auth] = _allow_dashboard_auth
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_updatestats_guard_prevents_null_error():
    """updateStats should return early on pages without dashboard stat elements."""
    js = Path("src/web/static/app.js").read_text(encoding="utf-8")

    assert "if (!document.getElementById('stat-total')) return;" in js


def test_incident_detail_renders_pd_metadata(_in_memory_store, client):
    _clear_incident_store(_in_memory_store)
    incident_id = "inc-pd-metadata"

    _add_processing_incident(
        _in_memory_store,
        incident_id=incident_id,
        title="Checkout timeout incident",
        source_url="https://pagerduty.com/incidents/PD123",
        metadata={
            "provider": "pagerduty",
            "status": "acknowledged",
            "urgency": "high",
            "assigned_to": ["Alice", "Bob"],
            "escalation_policy": "Critical EP",
            "description": "Checkout API timeout above SLO",
        },
    )

    response = client.get(f"/dashboard/incident/{incident_id}")

    assert response.status_code == 200
    assert "Incident Details" in response.text
    assert "Checkout API timeout above SLO" in response.text
    assert "PagerDuty" in response.text
    assert "Acknowledged" in response.text
    assert "High" in response.text
    assert "Alice, Bob" in response.text
    assert "Critical EP" in response.text

    _clear_incident_store(_in_memory_store)


def test_incident_detail_renders_without_metadata(_in_memory_store, client):
    _clear_incident_store(_in_memory_store)
    incident_id = "inc-no-metadata"

    _add_processing_incident(
        _in_memory_store,
        incident_id=incident_id,
        title="Title fallback when metadata missing",
        source="manual",
        metadata={},
    )

    response = client.get(f"/dashboard/incident/{incident_id}")

    assert response.status_code == 200
    assert "Incident Details" in response.text
    assert "Title fallback when metadata missing" in response.text
    assert "Unknown" in response.text

    _clear_incident_store(_in_memory_store)


def test_incident_detail_source_url_link(_in_memory_store, client):
    _clear_incident_store(_in_memory_store)
    incident_id = "inc-source-url"
    source_url = "https://pagerduty.com/incidents/PD-LINK"

    _add_processing_incident(
        _in_memory_store,
        incident_id=incident_id,
        title="PD source URL link test",
        source_url=source_url,
        metadata={"provider": "pagerduty", "status": "triggered"},
    )

    response = client.get(f"/dashboard/incident/{incident_id}")

    assert response.status_code == 200
    assert source_url in response.text
    assert "Open Incident" in response.text

    _clear_incident_store(_in_memory_store)


def test_incident_detail_assigned_to_display(_in_memory_store, client):
    _clear_incident_store(_in_memory_store)
    incident_id = "inc-assigned-to"

    _add_processing_incident(
        _in_memory_store,
        incident_id=incident_id,
        title="Assigned engineer display test",
        metadata={
            "provider": "pagerduty",
            "status": "triggered",
            "assigned_to": ["Primary Oncall", "Database SME"],
        },
    )

    response = client.get(f"/dashboard/incident/{incident_id}")

    assert response.status_code == 200
    assert "Primary Oncall, Database SME" in response.text

    _clear_incident_store(_in_memory_store)
