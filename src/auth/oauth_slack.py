"""Slack OAuth2 integration flow.

This is used to connect a Slack workspace to a tenant so Incident Copilot can:
- Post context cards (bot token)
- Join channels automatically

Slack OAuth is configured in your Slack App settings.
Docs: https://api.slack.com/authentication/oauth-v2
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..config import get_settings
from ..security import encrypt_json
from .middleware import AuthContext, get_auth_context, require_role
from .models import UserRole
from .service import auth_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/integrations/oauth/slack", tags=["integrations"])

# In-memory state storage (replace with Redis in production)
_slack_oauth_states: dict[str, dict] = {}


class SlackOAuthResponse(BaseModel):
    ok: bool
    access_token: str | None = None
    token_type: str | None = None
    scope: str | None = None
    bot_user_id: str | None = None
    app_id: str | None = None
    team: dict | None = None
    authed_user: dict | None = None
    error: str | None = None


class SlackOAuth:
    AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
    TOKEN_URL = "https://slack.com/api/oauth.v2.access"

    def __init__(self):
        settings = get_settings()
        self.client_id = getattr(settings, "slack_oauth_client_id", "")
        self.client_secret = getattr(settings, "slack_oauth_client_secret", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        # Bot scopes (what we need to post + react)
        bot_scopes = [
            "chat:write",
            "channels:read",
            "channels:join",
            "groups:read",
            "im:read",
            "mpim:read",
            "reactions:write",
        ]
        # User scopes (optional; Slack returns authed_user.access_token)
        user_scopes = [
            "users:read",
        ]

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": ",".join(bot_scopes),
            "user_scope": ",".join(user_scopes),
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> SlackOAuthResponse:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            data = resp.json()
            return SlackOAuthResponse(**data)


async def _slack_api(token: str, method: str, payload: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"https://slack.com/api/{method}",
            headers={"Authorization": f"Bearer {token}"},
            json=payload or {},
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("slack_api_error", method=method, error=data.get("error"))
        return data


@router.get("/start")
@require_role(UserRole.OWNER, UserRole.ADMIN)
async def start_slack_oauth(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    return_to: str | None = Query(default=None),
):
    """Start Slack OAuth for the current tenant."""
    settings = get_settings()
    oauth = SlackOAuth()
    if not oauth.is_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack OAuth is not configured (missing client id/secret)",
        )

    state = secrets.token_urlsafe(32)
    redirect_uri = f"{settings.app_url}/api/integrations/oauth/slack/callback"

    _slack_oauth_states[state] = {
        "tenant_id": auth.tenant_id,
        "user_id": auth.user_id,
        "redirect_uri": redirect_uri,
        "return_to": return_to or f"{settings.app_url}/dashboard/onboarding-wizard",
        "created_at": datetime.now(UTC).isoformat(),
    }

    return RedirectResponse(url=oauth.get_authorization_url(state, redirect_uri))


@router.get("/callback")
async def slack_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Slack OAuth callback."""
    settings = get_settings()

    if error:
        logger.warning("slack_oauth_denied", error=error)
        return RedirectResponse(
            url=f"{settings.app_url}/dashboard/onboarding-wizard?slack_error=denied"
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{settings.app_url}/dashboard/onboarding-wizard?slack_error=invalid"
        )

    state_data = _slack_oauth_states.pop(state, None)
    if not state_data:
        return RedirectResponse(
            url=f"{settings.app_url}/dashboard/onboarding-wizard?slack_error=state"
        )

    oauth = SlackOAuth()
    token = await oauth.exchange_code(code, state_data["redirect_uri"])
    if not token.ok or not token.access_token:
        logger.error("slack_oauth_token_failed", error=token.error)
        return RedirectResponse(
            url=f"{settings.app_url}/dashboard/onboarding-wizard?slack_error=token"
        )

    bot_token = token.access_token
    authed_user_token = None
    if token.authed_user and isinstance(token.authed_user, dict):
        authed_user_token = token.authed_user.get("access_token")

    # Attempt to join the default channel (best-effort)
    default_channel = getattr(settings, "slack_default_channel", "#incidents")
    # If it's a name like #incidents, we need an ID; skip unless user provides an ID.
    if default_channel and default_channel.startswith("C"):
        await _slack_api(bot_token, "conversations.join", {"channel": default_channel})

    integration_record = {
        "oauth": {
            "bot_token": bot_token,
            "authed_user_token": authed_user_token,
            "scope": token.scope,
            "team": token.team,
            "bot_user_id": token.bot_user_id,
            "app_id": token.app_id,
        },
        "connected_at": datetime.now(UTC).isoformat(),
    }

    await auth_service.update_tenant_integrations(
        state_data["tenant_id"],
        {"slack": {"encrypted": encrypt_json(integration_record)}},
    )

    return RedirectResponse(url=f"{state_data['return_to']}?slack=connected")
