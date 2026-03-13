"""Tests for Slack interaction handler."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.slack_interactions import handle_interaction


class TestHandleInteraction:
    @pytest.mark.asyncio
    async def test_ignores_non_block_actions(self):
        result = await handle_interaction({"type": "view_submission"})
        assert result is None

    @pytest.mark.asyncio
    async def test_ignores_empty_actions(self):
        result = await handle_interaction({"type": "block_actions", "actions": []})
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_memory_feedback(self):
        result = await handle_interaction(
            {
                "type": "block_actions",
                "actions": [{"action_id": "memory_feedback_helpful", "value": "{}"}],
                "user": {"id": "U1"},
                "channel": {"id": "C1"},
            }
        )
        assert result is None  # Deferred to existing handler

    @pytest.mark.asyncio
    async def test_action_approve(self):
        value = json.dumps({"action_id": "act-1", "incident_id": "INC-1"})

        with patch("src.integrations.slack_interactions._workflow") as mock_wf:
            mock_action = MagicMock()
            mock_action.description = "Rollback deploy"
            mock_wf.approve.return_value = mock_action

            with patch("src.integrations.slack_interactions._executor") as mock_exec:
                mock_result = MagicMock()
                mock_result.execution_result = {"status": "ok"}
                mock_exec.execute = AsyncMock(return_value=mock_result)

                result = await handle_interaction(
                    {
                        "type": "block_actions",
                        "actions": [
                            {"action_id": "action_approve:act-1", "value": value}
                        ],
                        "user": {"username": "alice"},
                        "channel": {"id": "C1"},
                    }
                )

        assert result is not None
        assert (
            "executed" in result.get("text", "").lower()
            or "approved" in result.get("text", "").lower()
        )

    @pytest.mark.asyncio
    async def test_action_reject(self):
        value = json.dumps({"action_id": "act-1", "incident_id": "INC-1"})

        with patch("src.integrations.slack_interactions._workflow") as mock_wf:
            mock_action = MagicMock()
            mock_action.description = "Rollback deploy"
            mock_wf.reject.return_value = mock_action

            result = await handle_interaction(
                {
                    "type": "block_actions",
                    "actions": [{"action_id": "action_reject:act-1", "value": value}],
                    "user": {"username": "bob"},
                    "channel": {"id": "C1"},
                }
            )

        assert result is not None
        assert "rejected" in result.get("text", "").lower()

    @pytest.mark.asyncio
    async def test_generate_postmortem(self):
        with patch(
            "src.integrations.slack_interactions._handle_generate_postmortem"
        ) as mock_pm:
            mock_pm.return_value = {
                "response_type": "ephemeral",
                "text": "Generating...",
            }

            result = await handle_interaction(
                {
                    "type": "block_actions",
                    "actions": [{"action_id": "generate_postmortem", "value": "INC-1"}],
                    "user": {"username": "alice"},
                    "channel": {"id": "C1"},
                }
            )

        assert result is not None
