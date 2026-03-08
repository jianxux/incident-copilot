"""Regression tests for incident detail page rendering and JS guards."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.main import create_app
from src.models import Severity
from src.web.routes import pages as pages_routes
from src.web.store import InMemoryIncidentStore
import src.web.store as web_store_module


incident_store = InMemoryIncidentStore(max_incidents=50)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _use_in_memory_incident_store(monkeypatch: pytest.MonkeyPatch):
    store = InMemoryIncidentStore(max_incidents=50)
    monkeypatch.setattr(web_store_module, "incident_store", store)
    monkeypatch.setattr(pages_routes, "incident_store", store)
    globals()["incident_store"] = store
    _clear_incident_store()
    yield
    _clear_incident_store()


def _clear_incident_store() -> None:
    if hasattr(incident_store, "_incidents"):
        incident_store._incidents.clear()
    if hasattr(incident_store, "_order"):
        incident_store._order.clear()


def _add_processing_incident(
    *,
    incident_id: str,
    title: str,
    tenant_id: str = "default",
    source: str = "pagerduty",
    source_url: str | None = None,
    metadata: dict | None = None,
) -> None:
    _run(
        incident_store.add_incident(
            incident_id=incident_id,
            title=title,
            service_name="payments-api",
            severity=Severity.HIGH,
            triggered_at=datetime.now(UTC),
            source=source,
            source_url=source_url,
            metadata=metadata,
            tenant_id=tenant_id,
        )
    )


def test_updatestats_guard_prevents_null_error():
    """updateStats should return early on pages without dashboard stat elements."""
    js = Path("src/web/static/app.js").read_text(encoding="utf-8")

    assert "if (!document.getElementById('stat-total')) return;" in js


def test_incident_detail_renders_pd_metadata():
    _clear_incident_store()
    incident_id = "inc-pd-metadata"

    _add_processing_incident(
        incident_id=incident_id,
        title="Checkout timeout incident",
        tenant_id="default",
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

    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/dashboard/incident/{incident_id}")

    assert response.status_code == 200
    assert "Incident Details" in response.text
    assert "Checkout API timeout above SLO" in response.text
    assert "PagerDuty" in response.text
    assert "Acknowledged" in response.text
    assert "High" in response.text
    assert "Alice, Bob" in response.text
    assert "Critical EP" in response.text

    _clear_incident_store()


def test_incident_detail_renders_without_metadata():
    _clear_incident_store()
    incident_id = "inc-no-metadata"

    _add_processing_incident(
        incident_id=incident_id,
        title="Title fallback when metadata missing",
        tenant_id="default",
        source="manual",
        metadata={},
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/dashboard/incident/{incident_id}")

    assert response.status_code == 200
    assert "Incident Details" in response.text
    assert "Title fallback when metadata missing" in response.text
    assert "Unknown" in response.text

    _clear_incident_store()


def test_incident_detail_source_url_link():
    _clear_incident_store()
    incident_id = "inc-source-url"
    source_url = "https://pagerduty.com/incidents/PD-LINK"

    _add_processing_incident(
        incident_id=incident_id,
        title="PD source URL link test",
        tenant_id="default",
        source_url=source_url,
        metadata={"provider": "pagerduty", "status": "triggered"},
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/dashboard/incident/{incident_id}")

    assert response.status_code == 200
    assert source_url in response.text
    assert "Open Incident" in response.text

    _clear_incident_store()


def test_incident_detail_assigned_to_display():
    _clear_incident_store()
    incident_id = "inc-assigned-to"

    _add_processing_incident(
        incident_id=incident_id,
        title="Assigned engineer display test",
        tenant_id="default",
        metadata={
            "provider": "pagerduty",
            "status": "triggered",
            "assigned_to": ["Primary Oncall", "Database SME"],
        },
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/dashboard/incident/{incident_id}")

    assert response.status_code == 200
    assert "Primary Oncall, Database SME" in response.text

    _clear_incident_store()
