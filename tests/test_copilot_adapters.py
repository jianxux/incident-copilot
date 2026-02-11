"""Tests for Copilot Slack and Web adapters."""

import asyncio
import hashlib
import hmac
import time
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.copilot.adapters import slack_adapter, web_adapter
from src.copilot.thread_registry import ThreadRegistry


class DummySettings:
    """Test settings container for adapter monkeypatching."""

    def __init__(self, signing_secret: str = "") -> None:
        self.slack_signing_secret = signing_secret
        self.slack_bot_token = "xoxb-test"


class FakeCopilot:
    """Simple async fake for Copilot integration tests."""

    def __init__(self) -> None:
        self.chat = AsyncMock(return_value="copilot response")
        self.generate_summary = AsyncMock(
            return_value={
                "title": "Summary",
                "summary": "Investigation summary",
                "root_cause": "Config drift",
                "resolution": "Rollback",
            }
        )
        self.suggest_next_steps = AsyncMock(return_value=["Check logs", "Rollback"])
        self.get_session = lambda incident_id: object()


class FakeWebCopilot:
    """Fake copilot for websocket tests."""

    def __init__(self) -> None:
        self.chat = AsyncMock(return_value="web response")
        self.generate_summary = AsyncMock(return_value={"summary": "web summary"})
        self.suggest_next_steps = AsyncMock(return_value=["step one", "step two"])
        self.get_session = lambda incident_id: object()
        self.get_or_create_session = AsyncMock()


class FakeSlackClient:
    """Slack API client fake."""

    def __init__(self) -> None:
        self.chat_postMessage = AsyncMock(return_value={"ok": True})


@pytest.fixture
def slack_app(monkeypatch):
    app = FastAPI()
    app.include_router(slack_adapter.router)

    monkeypatch.setattr(slack_adapter, "thread_registry", ThreadRegistry())
    monkeypatch.setattr(slack_adapter, "get_settings", lambda: DummySettings())
    monkeypatch.setattr(
        slack_adapter,
        "_rate_limiter",
        slack_adapter.IncidentRateLimiter(limit=10, window_seconds=60),
    )

    fake_copilot = FakeCopilot()
    fake_client = FakeSlackClient()
    monkeypatch.setattr(slack_adapter, "get_copilot", lambda: fake_copilot)
    monkeypatch.setattr(slack_adapter, "_get_slack_client", lambda: fake_client)

    client = TestClient(app)
    return client, fake_copilot, fake_client


@pytest.fixture
def web_app(monkeypatch):
    app = FastAPI()
    app.include_router(web_adapter.router)

    fake = FakeWebCopilot()
    monkeypatch.setattr(web_adapter, "get_web_copilot", lambda: fake)
    client = TestClient(app)
    return client, fake


def _signed_headers(body: bytes, secret: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    base = f"v0:{timestamp}:{body.decode('utf-8')}"
    digest = hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()
    return {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": f"v0={digest}",
        "Content-Type": "application/json",
    }


@pytest.mark.asyncio
async def test_thread_registry_register_and_lookup():
    registry = ThreadRegistry()
    await registry.register_thread("T1", "C1", "123.1", "INC-1")
    found = await registry.get_incident_id("T1", "C1", "123.1")
    assert found == "INC-1"


@pytest.mark.asyncio
async def test_thread_registry_missing_returns_none():
    registry = ThreadRegistry()
    found = await registry.get_incident_id("T1", "C1", "missing")
    assert found is None


def test_url_verification_challenge(slack_app):
    client, _, _ = slack_app
    payload = {"type": "url_verification", "challenge": "abc123"}

    response = client.post("/api/slack/events", json=payload)

    assert response.status_code == 200
    assert response.json() == {"challenge": "abc123"}


def test_events_invalid_signature_rejected(monkeypatch):
    app = FastAPI()
    app.include_router(slack_adapter.router)
    monkeypatch.setattr(slack_adapter, "thread_registry", ThreadRegistry())
    monkeypatch.setattr(
        slack_adapter,
        "get_settings",
        lambda: DummySettings(signing_secret="topsecret"),
    )

    client = TestClient(app)
    payload = {"type": "url_verification", "challenge": "xyz"}
    response = client.post("/api/slack/events", json=payload)

    assert response.status_code == 401


def test_message_event_happy_path(slack_app):
    client, fake_copilot, fake_client = slack_app

    asyncio.run(
        slack_adapter.thread_registry.register_thread("T1", "C1", "123.4", "INC-123")
    )

    payload = {
        "type": "event_callback",
        "team_id": "T1",
        "event": {
            "type": "message",
            "channel": "C1",
            "thread_ts": "123.4",
            "text": "What changed?",
            "user": "U1",
        },
    }

    response = client.post("/api/slack/events", json=payload)

    assert response.status_code == 200
    fake_copilot.chat.assert_awaited_once_with(
        incident_id="INC-123", user_message="What changed?"
    )
    fake_client.chat_postMessage.assert_awaited_once()


def test_bot_message_ignored(slack_app):
    client, fake_copilot, fake_client = slack_app

    payload = {
        "type": "event_callback",
        "team_id": "T1",
        "event": {
            "type": "message",
            "channel": "C1",
            "thread_ts": "123.4",
            "text": "Bot text",
            "bot_id": "B1",
            "user": "U1",
        },
    }

    response = client.post("/api/slack/events", json=payload)

    assert response.status_code == 200
    fake_copilot.chat.assert_not_awaited()
    fake_client.chat_postMessage.assert_not_awaited()


def test_non_thread_message_ignored(slack_app):
    client, fake_copilot, _ = slack_app

    payload = {
        "type": "event_callback",
        "team_id": "T1",
        "event": {
            "type": "message",
            "channel": "C1",
            "text": "No thread",
            "user": "U1",
        },
    }

    response = client.post("/api/slack/events", json=payload)

    assert response.status_code == 200
    fake_copilot.chat.assert_not_awaited()


def test_message_rate_limited(slack_app, monkeypatch):
    client, fake_copilot, _ = slack_app
    limiter = slack_adapter.IncidentRateLimiter(limit=0, window_seconds=60)
    monkeypatch.setattr(slack_adapter, "_rate_limiter", limiter)

    asyncio.run(
        slack_adapter.thread_registry.register_thread("T1", "C1", "123.4", "INC-123")
    )

    payload = {
        "type": "event_callback",
        "team_id": "T1",
        "event": {
            "type": "message",
            "channel": "C1",
            "thread_ts": "123.4",
            "text": "rate limit",
            "user": "U1",
        },
    }

    response = client.post("/api/slack/events", json=payload)

    assert response.status_code == 200
    fake_copilot.chat.assert_not_awaited()


def test_slash_command_summary(slack_app):
    client, _, _ = slack_app
    body = urlencode(
        {
            "command": "/copilot",
            "text": "summary INC-123",
            "team_id": "T1",
            "channel_id": "C1",
        }
    )
    response = client.post(
        "/api/slack/commands",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    assert "Summary" in response.json()["text"]


def test_slash_command_suggest(slack_app):
    client, _, _ = slack_app
    body = urlencode(
        {
            "command": "/copilot",
            "text": "suggest INC-123",
            "team_id": "T1",
            "channel_id": "C1",
        }
    )
    response = client.post(
        "/api/slack/commands",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    assert "Suggested next steps" in response.json()["text"]


def test_slash_command_unknown_action(slack_app):
    client, _, _ = slack_app
    body = urlencode(
        {
            "command": "/copilot",
            "text": "help INC-123",
            "team_id": "T1",
            "channel_id": "C1",
        }
    )
    response = client.post(
        "/api/slack/commands",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    assert "Use `/copilot summary" in response.json()["text"]


def test_slash_command_signature_verification(monkeypatch):
    app = FastAPI()
    app.include_router(slack_adapter.router)

    monkeypatch.setattr(slack_adapter, "thread_registry", ThreadRegistry())
    monkeypatch.setattr(
        slack_adapter,
        "get_settings",
        lambda: DummySettings(signing_secret="topsecret"),
    )

    client = TestClient(app)
    body = urlencode({"command": "/copilot", "text": "summary INC-123"}).encode()
    headers = _signed_headers(body, "topsecret")
    headers["Content-Type"] = "application/x-www-form-urlencoded"

    fake_copilot = FakeCopilot()
    monkeypatch.setattr(slack_adapter, "get_copilot", lambda: fake_copilot)

    response = client.post("/api/slack/commands", content=body, headers=headers)

    assert response.status_code == 200


def test_websocket_chat_exchange(web_app):
    client, fake = web_app

    with client.websocket_connect("/ws/copilot/INC-WS-1") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "system"

        websocket.send_json({"action": "chat", "message": "hello"})
        typing = websocket.receive_json()
        reply = websocket.receive_json()

        assert typing["type"] == "assistant_typing"
        assert reply["type"] == "assistant"
        assert reply["message"] == "web response"

    fake.chat.assert_awaited_once_with(incident_id="INC-WS-1", user_message="hello")


def test_websocket_summary_action(web_app):
    client, _ = web_app

    with client.websocket_connect("/ws/copilot/INC-WS-2") as websocket:
        websocket.receive_json()  # system
        websocket.send_json({"action": "summary", "message": ""})
        reply = websocket.receive_json()

        assert reply["type"] == "assistant"
        assert "web summary" in reply["message"]
