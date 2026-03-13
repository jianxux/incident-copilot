"""Tests for Slack lifecycle war room functions."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from slack_sdk.errors import SlackApiError

from src.integrations.slack_lifecycle import (
    build_incident_notification_blocks,
    create_warroom_from_notification,
    post_incident_notification,
    post_update_to_incident,
)
from src.integrations.slack_interactions import _handle_start_warroom


class TestBuildIncidentNotificationBlocks:
    def test_returns_blocks_with_header_and_button(self):
        blocks = build_incident_notification_blocks(
            incident_id="INC-12345678",
            title="High latency on payments-api",
            service="payments-api",
            severity="P1",
            triggered_at="2026-02-28T12:00:00Z",
            summary="Error rate spiked after deploy abc123",
        )
        assert isinstance(blocks, list)
        assert len(blocks) >= 3  # header, fields, summary, actions

        # Header contains severity badge
        header = blocks[0]
        assert header["type"] == "header"
        assert "🔴" in header["text"]["text"]

        # Actions block with war room button
        actions_block = [b for b in blocks if b["type"] == "actions"]
        assert len(actions_block) == 1
        button = actions_block[0]["elements"][0]
        assert button["action_id"] == "start_warroom"
        value = json.loads(button["value"])
        assert value["incident_id"] == "INC-12345678"
        assert value["service"] == "payments-api"

    def test_severity_badges(self):
        for sev, emoji in [("P1", "🔴"), ("P2", "🟠"), ("P3", "🟡"), ("P4", "🟢")]:
            blocks = build_incident_notification_blocks(
                incident_id="INC-1",
                title="Test",
                service="svc",
                severity=sev,
                triggered_at="now",
            )
            assert emoji in blocks[0]["text"]["text"]

    def test_no_summary_omits_section(self):
        blocks = build_incident_notification_blocks(
            incident_id="INC-1",
            title="Test",
            service="svc",
            severity="P3",
            triggered_at="now",
            summary=None,
        )
        # Should have header, fields, actions (no summary section)
        types = [b["type"] for b in blocks]
        assert types == ["header", "section", "actions"]


class TestPostIncidentNotification:
    @pytest.mark.asyncio
    async def test_posts_to_channel(self):
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {
            "ok": True,
            "ts": "1234.5678",
            "channel": "C999",
        }

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            result = await post_incident_notification(
                tenant_id=None,
                channel="#incidents",
                incident_id="INC-001",
                title="DB down",
                service="db-api",
                severity="P1",
                triggered_at="2026-02-28T12:00:00Z",
                summary="Database connection pool exhausted",
            )

        assert result is not None
        assert result["ts"] == "1234.5678"
        assert result["channel_id"] == "C999"
        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "#incidents"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_client(self):
        with patch(
            "src.integrations.slack_lifecycle.get_slack_client", return_value=None
        ):
            result = await post_incident_notification(
                tenant_id=None,
                channel="#incidents",
                incident_id="INC-001",
                title="Test",
                service="svc",
                severity="P2",
                triggered_at="now",
            )
        assert result is None


class TestCreateWarroomFromNotification:
    @pytest.mark.asyncio
    async def test_creates_channel_and_posts_back(self):
        mock_client = AsyncMock()
        mock_client.conversations_create.return_value = {
            "ok": True,
            "channel": {"id": "C_WARROOM"},
        }
        mock_client.conversations_setTopic.return_value = {"ok": True}
        mock_client.chat_postMessage.return_value = {"ok": True, "ts": "111.222"}

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            result = await create_warroom_from_notification(
                tenant_id=None,
                incident_id="INC-12345678",
                service="payments-api",
                original_channel_id="C_INCIDENTS",
                original_ts="100.200",
                context_blocks=[
                    {"type": "section", "text": {"type": "mrkdwn", "text": "test"}}
                ],
            )

        assert result is not None
        assert result["channel_id"] == "C_WARROOM"
        # Should have posted context card + backlink = 2 chat_postMessage calls
        assert mock_client.chat_postMessage.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_on_failure(self):
        mock_client = AsyncMock()
        mock_client.conversations_create.return_value = {
            "ok": False,
            "error": "name_taken",
        }

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            with pytest.raises(RuntimeError, match="name_taken"):
                await create_warroom_from_notification(
                    tenant_id=None,
                    incident_id="INC-001",
                    service="svc",
                )

    @pytest.mark.asyncio
    async def test_missing_scopes_error_surfaces(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.data = {"ok": False, "error": "missing_scope"}
        mock_client.conversations_create.side_effect = SlackApiError(
            message="missing_scope",
            response=mock_response,
        )

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            with pytest.raises(RuntimeError, match="missing_scope"):
                await create_warroom_from_notification(
                    tenant_id=None,
                    incident_id="INC-001",
                    service="svc",
                )

    @pytest.mark.asyncio
    async def test_raises_on_api_failure(self):
        mock_client = AsyncMock()
        mock_client.conversations_create.return_value = {
            "ok": False,
            "error": "restricted_action",
        }

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            with pytest.raises(RuntimeError, match="restricted_action"):
                await create_warroom_from_notification(
                    tenant_id=None,
                    incident_id="INC-001",
                    service="svc",
                )


class TestHandleStartWarroom:
    @pytest.mark.asyncio
    async def test_extracts_original_ts_from_payload(self):
        payload = {
            "actions": [
                {
                    "action_id": "start_warroom",
                    "value": json.dumps(
                        {
                            "incident_id": "INC-123",
                            "service": "payments-api",
                        }
                    ),
                }
            ],
            "user": {"username": "alice"},
            "channel": {"id": "C_ORIG"},
            "team": {"id": "T_TEAM1"},
            "message": {"ts": "123.456"},
        }

        with patch(
            "src.integrations.slack_interactions.create_warroom_from_notification",
            new=AsyncMock(
                return_value={
                    "channel_id": "C_WAR",
                    "channel_name": "inc-inc-123-payments-api",
                }
            ),
        ) as mock_create:
            await _handle_start_warroom(payload)

        mock_create.assert_awaited_once()
        assert mock_create.call_args.kwargs["original_ts"] == "123.456"
        assert mock_create.call_args.kwargs["tenant_id"] == "T_TEAM1"

    @pytest.mark.asyncio
    async def test_shows_error_detail_on_failure(self):
        payload = {
            "actions": [
                {
                    "action_id": "start_warroom",
                    "value": json.dumps(
                        {
                            "incident_id": "INC-123",
                            "service": "payments-api",
                        }
                    ),
                }
            ],
            "user": {"username": "alice"},
            "channel": {"id": "C_ORIG"},
            "team": {"id": "T_TEAM1"},
            "message": {"ts": "123.456"},
        }

        with patch(
            "src.integrations.slack_interactions.create_warroom_from_notification",
            new=AsyncMock(side_effect=RuntimeError("missing_scope: channels:write")),
        ):
            result = await _handle_start_warroom(payload)

        assert result is not None
        assert "missing_scope: channels:write" in result["text"]

    @pytest.mark.asyncio
    async def test_extracts_ts_from_container_fallback(self):
        payload = {
            "actions": [
                {
                    "action_id": "start_warroom",
                    "value": json.dumps(
                        {
                            "incident_id": "INC-123",
                            "service": "payments-api",
                        }
                    ),
                }
            ],
            "user": {"username": "alice"},
            "channel": {"id": "C_ORIG"},
            "team": {"id": "T_TEAM1"},
            "container": {"message_ts": "789.012"},
        }

        with patch(
            "src.integrations.slack_interactions.create_warroom_from_notification",
            new=AsyncMock(
                return_value={
                    "channel_id": "C_WAR",
                    "channel_name": "inc-inc-123-payments-api",
                }
            ),
        ) as mock_create:
            await _handle_start_warroom(payload)

        mock_create.assert_awaited_once()
        assert mock_create.call_args.kwargs["original_ts"] == "789.012"


class TestPostUpdateToIncident:
    @pytest.mark.asyncio
    async def test_posts_to_warroom_when_exists(self):
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ok": True}

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            ok = await post_update_to_incident(
                tenant_id=None,
                warroom_channel_id="C_WARROOM",
                incidents_channel_id="C_INCIDENTS",
                original_ts="100.200",
                text="Status update",
            )

        assert ok is True
        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C_WARROOM"
        assert "thread_ts" not in call_kwargs

    @pytest.mark.asyncio
    async def test_threads_in_incidents_when_no_warroom(self):
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ok": True}

        with patch(
            "src.integrations.slack_lifecycle.get_slack_client",
            return_value=mock_client,
        ):
            ok = await post_update_to_incident(
                tenant_id=None,
                warroom_channel_id=None,
                incidents_channel_id="C_INCIDENTS",
                original_ts="100.200",
                text="Status update",
            )

        assert ok is True
        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C_INCIDENTS"
        assert call_kwargs["thread_ts"] == "100.200"

    @pytest.mark.asyncio
    async def test_returns_false_no_client(self):
        with patch(
            "src.integrations.slack_lifecycle.get_slack_client", return_value=None
        ):
            ok = await post_update_to_incident(
                tenant_id=None,
                warroom_channel_id=None,
                incidents_channel_id=None,
                original_ts=None,
                text="test",
            )
        assert ok is False
