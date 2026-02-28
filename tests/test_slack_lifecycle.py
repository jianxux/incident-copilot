"""Tests for Slack incident lifecycle management."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.slack_lifecycle import (
    archive_channel,
    create_incident_channel,
    get_slack_client,
    post_context_card,
    post_status_update,
    post_suggested_actions,
    sanitize_channel_name,
    schedule_archive,
    update_context_card,
)


class TestSanitizeChannelName:
    def test_basic(self):
        assert sanitize_channel_name("abc123", "payments-api") == "inc-abc123-payments-api"

    def test_uppercase(self):
        assert sanitize_channel_name("ABC", "MyService") == "inc-abc-myservice"

    def test_special_chars(self):
        assert sanitize_channel_name("123", "my.service/v2") == "inc-123-my-service-v2"

    def test_max_length(self):
        result = sanitize_channel_name("a" * 50, "b" * 50)
        assert len(result) <= 80

    def test_strips_trailing_hyphens(self):
        result = sanitize_channel_name("id", "svc---")
        assert not result.endswith("-")


class TestGetSlackClient:
    @pytest.mark.asyncio
    async def test_uses_oauth_token_when_available(self):
        settings = MagicMock()
        settings.slack_bot_token = "xoxb-env-token"

        with patch(
            "src.integrations.slack_lifecycle.oauth_token_store"
        ) as mock_store:
            mock_store.get_access_token = AsyncMock(return_value="xoxb-oauth-token")
            client = await get_slack_client("tenant-1", settings)
            assert client is not None
            assert client.token == "xoxb-oauth-token"

    @pytest.mark.asyncio
    async def test_falls_back_to_env_var(self):
        settings = MagicMock()
        settings.slack_bot_token = "xoxb-env-token"

        with patch(
            "src.integrations.slack_lifecycle.oauth_token_store"
        ) as mock_store:
            mock_store.get_access_token = AsyncMock(return_value=None)
            client = await get_slack_client("tenant-1", settings)
            assert client is not None
            assert client.token == "xoxb-env-token"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_token(self):
        settings = MagicMock()
        settings.slack_bot_token = ""

        with patch(
            "src.integrations.slack_lifecycle.oauth_token_store"
        ) as mock_store:
            mock_store.get_access_token = AsyncMock(return_value=None)
            client = await get_slack_client(None, settings)
            assert client is None


class TestCreateIncidentChannel:
    @pytest.mark.asyncio
    async def test_creates_channel_and_sets_topic(self):
        mock_client = AsyncMock()
        mock_client.conversations_create.return_value = {
            "ok": True,
            "channel": {"id": "C123ABC"},
        }
        mock_client.conversations_setTopic.return_value = {"ok": True}

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            result = await create_incident_channel(
                tenant_id="t1",
                short_id="inc001",
                service_name="payments",
                title="High latency",
            )

        assert result is not None
        assert result["channel_id"] == "C123ABC"
        mock_client.conversations_create.assert_called_once()
        mock_client.conversations_setTopic.assert_called_once()

    @pytest.mark.asyncio
    async def test_invites_responders(self):
        mock_client = AsyncMock()
        mock_client.conversations_create.return_value = {
            "ok": True,
            "channel": {"id": "C123"},
        }

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            await create_incident_channel(
                tenant_id=None,
                short_id="x",
                service_name="svc",
                title="t",
                responder_slack_ids=["U1", "U2"],
            )

        assert mock_client.conversations_invite.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_none_when_no_client(self):
        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=None,
        ):
            result = await create_incident_channel(None, "x", "svc", "t")
            assert result is None


class TestPostContextCard:
    @pytest.mark.asyncio
    async def test_posts_and_returns_ts(self):
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ok": True, "ts": "1234.5678"}

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            ts = await post_context_card(None, "C123", [{"type": "section"}], "test")
            assert ts == "1234.5678"


class TestUpdateContextCard:
    @pytest.mark.asyncio
    async def test_updates_message(self):
        mock_client = AsyncMock()
        mock_client.chat_update.return_value = {"ok": True}

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            ok = await update_context_card(None, "C123", "1234.5678", [], "text")
            assert ok is True
            mock_client.chat_update.assert_called_once()


class TestPostSuggestedActions:
    @pytest.mark.asyncio
    async def test_posts_action_buttons(self):
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ok": True, "ts": "action.ts"}

        mock_action = MagicMock()
        mock_action.id = "act-1"
        mock_action.description = "Rollback deploy"
        mock_action.risk_level = MagicMock(value="high")
        mock_action.requires_approval = True

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            ts = await post_suggested_actions(None, "C123", [mock_action], "INC-1")
            assert ts == "action.ts"

        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        blocks = call_kwargs["blocks"]
        # Should have header + section + actions for each action
        assert any(b["type"] == "actions" for b in blocks)


class TestPostStatusUpdate:
    @pytest.mark.asyncio
    async def test_resolved_includes_postmortem_button(self):
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ok": True}

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            ok = await post_status_update(
                None, "C123", "resolved", "Incident resolved", incident_id="INC-1"
            )
            assert ok is True

        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        blocks = call_kwargs["blocks"]
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        assert len(action_blocks) == 1
        assert action_blocks[0]["elements"][0]["action_id"] == "generate_postmortem"

    @pytest.mark.asyncio
    async def test_acknowledged_no_postmortem_button(self):
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ok": True}

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            await post_status_update(None, "C123", "acknowledged", "Acked")

        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        blocks = call_kwargs["blocks"]
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        assert len(action_blocks) == 0


class TestArchiveChannel:
    @pytest.mark.asyncio
    async def test_archives(self):
        mock_client = AsyncMock()
        mock_client.conversations_archive.return_value = {"ok": True}

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            ok = await archive_channel(None, "C123")
            assert ok is True
