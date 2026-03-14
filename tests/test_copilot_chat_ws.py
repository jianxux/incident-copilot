"""Tests for copilot chat websocket reconnect and page rendering behavior."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from src.main import create_app
from src.models import Severity
from src.web.routes import incident_store


def _run(coro):
    return asyncio.run(coro)


def _clear_incident_store() -> None:
    if hasattr(incident_store, "_incidents"):
        incident_store._incidents.clear()
    if hasattr(incident_store, "_order"):
        incident_store._order.clear()


def _add_processing_incident(*, incident_id: str, title: str) -> None:
    _run(
        incident_store.add_incident(
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


def test_copilot_chat_page_renders():
    _clear_incident_store()
    incident_id = "inc-chat-ws-render"
    _add_processing_incident(
        incident_id=incident_id, title="Chat page render test incident"
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/dashboard/incident/{incident_id}/chat")

    assert response.status_code == 200
    assert "Copilot Chat" in response.text
    assert "Connected to incident copilot" in response.text
    assert "connection-status-dot" in response.text
    assert "connection-status-text" in response.text

    _clear_incident_store()


def test_copilot_chat_plural_copilot_alias_renders():
    _clear_incident_store()
    incident_id = "inc-chat-ws-alias"
    _add_processing_incident(
        incident_id=incident_id, title="Chat page alias test incident"
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/dashboard/incidents/{incident_id}/copilot")

    assert response.status_code == 200
    assert "Copilot Chat" in response.text

    _clear_incident_store()
