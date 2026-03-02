"""Tests for Slack OAuth callback behavior."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.auth.middleware import AuthContext
from src.auth.models import Tenant, User, UserRole
from src.auth.oauth_slack import SlackOAuthResponse, slack_oauth_callback, start_slack_oauth


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
        patch("src.auth.oauth_slack.register_slack_team_mapping") as mock_register_mapping,
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
        tenant_id="app-tenant-123",
        provider="slack",
        access_token="xoxb-bot-token",
    )
    mock_register_mapping.assert_called_once_with(
        team_id="T123SLACK",
        tenant_id="app-tenant-123",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_slack_oauth_uses_oauth_token_store_state():
    mock_settings = MagicMock()
    mock_settings.app_url = "https://app.example.com"
    auth = AuthContext(
        user=User(
            id="user-1",
            email="owner@example.com",
            name="Owner",
            tenant_id="tenant-1",
            role=UserRole.OWNER,
        ),
        tenant=Tenant(id="tenant-1", name="Tenant", slug="tenant"),
    )

    with (
        patch("src.auth.oauth_slack.get_settings", return_value=mock_settings),
        patch("src.auth.oauth_slack.oauth_token_store") as mock_token_store,
        patch("src.auth.oauth_slack.SlackOAuth") as mock_oauth_cls,
    ):
        mock_token_store.save_state = AsyncMock(return_value="nonce-123")
        mock_oauth = mock_oauth_cls.return_value
        mock_oauth.is_configured = True
        mock_oauth.get_authorization_url.return_value = "https://slack.com/oauth/v2/authorize?client_id=test&state=nonce-123&scope=test"

        response = await start_slack_oauth(
            request=MagicMock(headers={"accept": "application/json"}),
            auth=auth,
            return_to=None,
        )

    assert "redirect_url" in response
    parsed = urlparse(response["redirect_url"])
    params = parse_qs(parsed.query)
    assert params["state"][0] == "nonce-123"
    mock_token_store.save_state.assert_awaited_once()
    call_kwargs = mock_token_store.save_state.call_args.kwargs
    assert call_kwargs["provider"] == "slack"
    assert call_kwargs["tenant_id"] == "tenant-1"
    assert call_kwargs["user_id"] == "user-1"
    assert call_kwargs["redirect_uri"] == "https://app.example.com/api/integrations/oauth/slack/callback"
    # return_to falls back to app_url/dashboard/onboarding-wizard when param is None
    assert "onboarding-wizard" in str(call_kwargs["return_to"])
