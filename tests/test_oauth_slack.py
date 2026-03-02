"""Tests for legacy Slack OAuth callback behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.auth.oauth_slack import SlackOAuthResponse, slack_oauth_callback


@pytest.mark.unit
@pytest.mark.asyncio
async def test_slack_oauth_callback_stores_token_in_both_locations():
    state_data = {
        "tenant_id": "app-tenant-123",
        "redirect_uri": "https://app.example.com/api/integrations/oauth/slack/callback",
        "return_to": "https://app.example.com/dashboard/onboarding-wizard",
    }
    token = SlackOAuthResponse(
        ok=True,
        access_token="xoxb-bot-token",
        scope="chat:write",
        team={"id": "T123SLACK", "name": "Workspace"},
    )
    mock_settings = MagicMock()
    mock_settings.app_url = "https://app.example.com"
    mock_settings.slack_default_channel = "#incidents"

    with (
        patch("src.auth.oauth_slack.get_settings", return_value=mock_settings),
        patch("src.auth.oauth_slack.oauth_state_store") as mock_state_store,
        patch("src.auth.oauth_slack.SlackOAuth") as mock_oauth_cls,
        patch("src.auth.oauth_slack.auth_service") as mock_auth_service,
        patch("src.auth.oauth_slack.oauth_token_store") as mock_token_store,
    ):
        mock_state_store.consume = AsyncMock(return_value=state_data)
        mock_auth_service.update_tenant_integrations = AsyncMock()
        mock_token_store.upsert_token = AsyncMock()
        mock_oauth = mock_oauth_cls.return_value
        mock_oauth.exchange_code = AsyncMock(return_value=token)

        response = await slack_oauth_callback(
            request=MagicMock(),
            code="oauth-code",
            state="oauth-state",
        )

    assert response.headers["location"].endswith("?slack=connected")
    mock_auth_service.update_tenant_integrations.assert_awaited_once()
    auth_args, _ = mock_auth_service.update_tenant_integrations.await_args
    assert auth_args[0] == "app-tenant-123"
    mock_token_store.upsert_token.assert_awaited_once_with(
        tenant_id="T123SLACK",
        provider="slack",
        access_token="xoxb-bot-token",
    )
