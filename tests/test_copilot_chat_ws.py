"""Tests for copilot chat websocket reconnect and page rendering behavior."""

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


def _add_processing_incident(store, *, incident_id: str, title: str) -> None:
    _run(
        store.add_incident(
            incident_id=incident_id,
            title=title,
            service_name="payments-api",
            severity=Severity.HIGH,
            triggered_at=datetime.now(UTC),
            source="pagerduty",
            source_url="https://pagerduty.com/incidents/TEST123",
            metadata={"description": "Copilot chat websocket test incident"},
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


def test_copilot_chat_has_reconnect_logic():
    template = Path("src/web/templates/copilot_chat.html").read_text(encoding="utf-8")

    assert "function connect()" in template
    assert "function scheduleReconnect()" in template
    assert "MAX_RECONNECT_ATTEMPTS = 10" in template
    assert "BASE_RECONNECT_DELAY_MS * (2 ** reconnectAttempts)" in template
    assert "MAX_RECONNECT_DELAY_MS" in template
    assert "Reconnected to copilot" in template
    assert "Connection lost. Refresh to retry." in template


def test_copilot_chat_checks_ws_readystate():
    template = Path("src/web/templates/copilot_chat.html").read_text(encoding="utf-8")

    assert "ws && ws.readyState === WebSocket.OPEN" in template
    assert "function sendPayload(payload)" in template


def test_copilot_chat_page_renders(_in_memory_store, client):
    _clear_incident_store(_in_memory_store)
    incident_id = "inc-chat-ws-render"
    _add_processing_incident(
        _in_memory_store,
        incident_id=incident_id,
        title="Chat page render test incident",
    )

    response = client.get(f"/dashboard/incident/{incident_id}/chat")

    assert response.status_code == 200
    assert "Copilot Chat" in response.text
    assert "Connected to incident copilot" in response.text
    assert "connection-status-dot" in response.text
    assert "connection-status-text" in response.text

    _clear_incident_store(_in_memory_store)
