"""Tests for Microsoft Teams Bot Framework adapter."""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.copilot.adapters import teams_adapter
from src.copilot.adapters.teams_adapter import (
    IncidentRateLimiter,
    TeamsThreadRegistry,
    build_context_card,
    build_suggestions_card,
    build_verdict_card,
    verify_teams_signature,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class DummySettings:
    teams_app_id = "test-app-id"
    teams_app_password = ""
    teams_bot_id = "bot-123"


class FakeSession:
    incident_id = "INC-123"
    service_name = "payments-api"
    messages = []
    context_card = None
    created_at = datetime.now(timezone.utc)
    updated_at = datetime.now(timezone.utc)


@pytest.fixture()
def fake_copilot():
    copilot = MagicMock()
    copilot.chat = AsyncMock(return_value="AI response")
    copilot.get_session = MagicMock(return_value=FakeSession())
    copilot.generate_summary = AsyncMock(
        return_value={
            "title": "Test Incident",
            "summary": "Something broke",
            "root_cause": "Bad deploy",
            "resolution": "Rolled back",
        }
    )
    copilot.suggest_next_steps = AsyncMock(return_value=["Check logs", "Rollback"])
    return copilot


@pytest.fixture()
def app_client(monkeypatch, fake_copilot):
    """Create a test app with Teams adapter routes."""
    app = FastAPI()
    app.include_router(teams_adapter.router)

    registry = TeamsThreadRegistry()
    monkeypatch.setattr(teams_adapter, "thread_registry", registry)
    monkeypatch.setattr(teams_adapter, "get_settings", lambda: DummySettings())
    monkeypatch.setattr(
        teams_adapter,
        "_rate_limiter",
        teams_adapter.IncidentRateLimiter(limit=10, window_seconds=60),
    )
    monkeypatch.setattr(teams_adapter, "get_copilot", lambda: fake_copilot)
    # Mock send functions to avoid real HTTP calls
    monkeypatch.setattr(teams_adapter, "send_text_reply", AsyncMock())
    monkeypatch.setattr(teams_adapter, "send_card", AsyncMock())

    return app, registry


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


class TestSignatureVerification:
    def test_no_password_allows_all(self):
        assert verify_teams_signature(b"body", None, "app", "") is True

    def test_missing_authorization_rejected(self):
        assert verify_teams_signature(b"body", None, "app", "secret") is False

    def test_hmac_valid(self):
        body = b'{"type":"message"}'
        secret = "my-secret"
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert verify_teams_signature(body, f"HMAC {digest}", "app", secret) is True

    def test_hmac_invalid(self):
        assert verify_teams_signature(b"body", "HMAC bad", "app", "secret") is False

    def test_bearer_accepted(self):
        assert (
            verify_teams_signature(b"body", "Bearer some-jwt", "app", "secret") is True
        )

    def test_malformed_header(self):
        assert verify_teams_signature(b"body", "noscheme", "app", "secret") is False


# ---------------------------------------------------------------------------
# Thread registry
# ---------------------------------------------------------------------------


class TestTeamsThreadRegistry:
    @pytest.mark.asyncio()
    async def test_register_and_lookup(self):
        reg = TeamsThreadRegistry()
        await reg.register("conv-1", "INC-100")
        assert await reg.get_incident_id("conv-1") == "INC-100"

    @pytest.mark.asyncio()
    async def test_unknown_conversation(self):
        reg = TeamsThreadRegistry()
        assert await reg.get_incident_id("unknown") is None


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_allows_within_limit(self):
        rl = IncidentRateLimiter(limit=3, window_seconds=60)
        assert rl.allow("INC-1") is True
        assert rl.allow("INC-1") is True
        assert rl.allow("INC-1") is True

    def test_blocks_over_limit(self):
        rl = IncidentRateLimiter(limit=0, window_seconds=60)
        assert rl.allow("INC-1") is False


# ---------------------------------------------------------------------------
# Adaptive card builders
# ---------------------------------------------------------------------------


class TestAdaptiveCards:
    def test_context_card_structure(self):
        card = build_context_card(
            {
                "title": "Outage",
                "summary": "Service down",
                "root_cause": "OOM",
                "resolution": "Restart",
            }
        )
        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.4"
        assert any(b.get("text") == "Outage" for b in card["body"])

    def test_context_card_defaults(self):
        card = build_context_card({})
        texts = [b.get("text") for b in card["body"]]
        assert "Incident Summary" in texts

    def test_verdict_card(self):
        card = build_verdict_card("INC-1", "Likely OOM", "85%")
        assert card["type"] == "AdaptiveCard"
        assert any("Confidence" in (b.get("text") or "") for b in card["body"])

    def test_suggestions_card(self):
        card = build_suggestions_card(["Check logs", "Rollback"])
        assert card["type"] == "AdaptiveCard"
        assert any("Check logs" in (b.get("text") or "") for b in card["body"])

    def test_suggestions_card_empty(self):
        card = build_suggestions_card([])
        assert card["type"] == "AdaptiveCard"


# ---------------------------------------------------------------------------
# Messages endpoint
# ---------------------------------------------------------------------------


class TestMessagesEndpoint:
    @pytest.mark.asyncio()
    async def test_message_triggers_copilot(self, app_client, fake_copilot):
        app, registry = app_client
        await registry.register("conv-1", "INC-123")

        activity = {
            "type": "message",
            "text": "What happened?",
            "conversation": {"id": "conv-1"},
            "from": {"id": "user-1"},
            "serviceUrl": "https://smba.trafficmanager.net/teams/",
            "id": "act-1",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/teams/messages", json=activity)
        assert resp.status_code == 200
        fake_copilot.chat.assert_awaited_once()
        teams_adapter.send_text_reply.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_bot_messages_ignored(self, app_client, fake_copilot):
        app, registry = app_client

        activity = {
            "type": "message",
            "text": "I am the bot",
            "conversation": {"id": "conv-1"},
            "from": {"id": "bot-123"},
            "serviceUrl": "https://smba.trafficmanager.net/teams/",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/teams/messages", json=activity)
        assert resp.status_code == 200
        fake_copilot.chat.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_empty_text_ignored(self, app_client, fake_copilot):
        app, _ = app_client

        activity = {
            "type": "message",
            "text": "",
            "conversation": {"id": "conv-1"},
            "from": {"id": "user-1"},
            "serviceUrl": "https://smba.trafficmanager.net/teams/",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/teams/messages", json=activity)
        assert resp.status_code == 200
        fake_copilot.chat.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_unmapped_conversation_ignored(self, app_client, fake_copilot):
        app, _ = app_client

        activity = {
            "type": "message",
            "text": "Hello",
            "conversation": {"id": "unknown-conv"},
            "from": {"id": "user-1"},
            "serviceUrl": "https://smba.trafficmanager.net/teams/",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/teams/messages", json=activity)
        assert resp.status_code == 200
        fake_copilot.chat.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_rate_limited_message(self, app_client, monkeypatch, fake_copilot):
        app, registry = app_client
        await registry.register("conv-1", "INC-123")
        monkeypatch.setattr(
            teams_adapter,
            "_rate_limiter",
            IncidentRateLimiter(limit=0, window_seconds=60),
        )

        activity = {
            "type": "message",
            "text": "Hello",
            "conversation": {"id": "conv-1"},
            "from": {"id": "user-1"},
            "serviceUrl": "https://smba.trafficmanager.net/teams/",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/teams/messages", json=activity)
        assert resp.status_code == 200
        fake_copilot.chat.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_invalid_auth_rejected(self, monkeypatch):
        app = FastAPI()
        app.include_router(teams_adapter.router)

        settings = DummySettings()
        settings.teams_app_password = "real-secret"
        monkeypatch.setattr(teams_adapter, "get_settings", lambda: settings)

        activity = {
            "type": "message",
            "text": "hi",
            "conversation": {"id": "c"},
            "from": {"id": "u"},
        }

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/teams/messages", json=activity)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Commands endpoint
# ---------------------------------------------------------------------------


class TestCommandsEndpoint:
    @pytest.mark.asyncio()
    async def test_summary_command(self, app_client, fake_copilot):
        app, _ = app_client

        payload = {"text": "summary INC-123", "conversation": {"id": "conv-1"}}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/teams/commands", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "Test Incident" in data["text"]

    @pytest.mark.asyncio()
    async def test_suggest_command(self, app_client, fake_copilot):
        app, _ = app_client

        payload = {"text": "suggest INC-123", "conversation": {"id": "conv-1"}}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/teams/commands", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "Check logs" in data["text"]

    @pytest.mark.asyncio()
    async def test_invalid_action(self, app_client):
        app, _ = app_client

        payload = {"text": "unknown", "conversation": {"id": "conv-1"}}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/teams/commands", json=payload)
        assert resp.status_code == 200
        assert "summary" in resp.json()["text"].lower()

    @pytest.mark.asyncio()
    async def test_missing_incident(self, app_client, fake_copilot):
        app, _ = app_client

        payload = {"text": "summary", "conversation": {"id": "conv-1"}}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/teams/commands", json=payload)
        assert resp.status_code == 200
        assert "No incident" in resp.json()["text"]

    @pytest.mark.asyncio()
    async def test_no_session(self, app_client, fake_copilot):
        app, _ = app_client
        fake_copilot.get_session = MagicMock(return_value=None)

        payload = {"text": "summary INC-999", "conversation": {"id": "conv-1"}}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/teams/commands", json=payload)
        assert resp.status_code == 200
        assert "No active" in resp.json()["text"]


# ---------------------------------------------------------------------------
# Slash commands inside messages
# ---------------------------------------------------------------------------


class TestSlashCommandInMessage:
    @pytest.mark.asyncio()
    async def test_copilot_summary_in_message(self, app_client, fake_copilot):
        app, _ = app_client

        activity = {
            "type": "message",
            "text": "/copilot summary INC-123",
            "conversation": {"id": "conv-1"},
            "from": {"id": "user-1"},
            "serviceUrl": "https://smba.trafficmanager.net/teams/",
            "id": "act-1",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/teams/messages", json=activity)
        assert resp.status_code == 200
        teams_adapter.send_card.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_incident_suggest_in_message(self, app_client, fake_copilot):
        app, _ = app_client

        activity = {
            "type": "message",
            "text": "/incident suggest INC-123",
            "conversation": {"id": "conv-1"},
            "from": {"id": "user-1"},
            "serviceUrl": "https://smba.trafficmanager.net/teams/",
            "id": "act-1",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/teams/messages", json=activity)
        assert resp.status_code == 200
        teams_adapter.send_card.assert_awaited()


# ---------------------------------------------------------------------------
# Channel notifications
# ---------------------------------------------------------------------------


class TestChannelNotifications:
    @pytest.mark.asyncio()
    async def test_notify_channel_builds_card(self):
        with patch.object(
            teams_adapter, "send_card", new_callable=AsyncMock
        ) as mock_send:
            from src.copilot.adapters.teams_adapter import notify_channel

            await notify_channel(
                "https://smba.trafficmanager.net/teams/",
                "conv-1",
                "INC-100",
                "Service recovered",
            )
            mock_send.assert_awaited_once()
            card = mock_send.call_args[0][2]
            assert card["type"] == "AdaptiveCard"
            assert any("INC-100" in (b.get("text") or "") for b in card["body"])
