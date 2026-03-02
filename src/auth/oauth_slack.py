"""Slack OAuth2 integration flow.

This is used to connect a Slack workspace to a tenant so Incident Copilot can:
- Post context cards (bot token)
- Join channels automatically

Slack OAuth is configured in your Slack App settings.
Docs: https://api.slack.com/authentication/oauth-v2
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..config import get_settings
from ..integrations.oauth_tokens import oauth_token_store
from ..integrations.slack_lifecycle import register_slack_team_mapping
from ..onboarding import oauth_state_store
from ..security import encrypt_json
from .middleware import AuthContext, get_auth_context, require_role
from .models import UserRole
from .service import auth_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/integrations/oauth/slack", tags=["integrations"])


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
        # Bot scopes (workspace-level bot token permissions)
        bot_scopes = [
            "chat:write",  # Post incident updates and responses
            "channels:read",  # Discover public channels
            "channels:join",  # Join public incident channels
            "channels:write",  # Create/rename/archive public war-room channels
            "channels:manage",  # Manage public channel settings (including archive flows)
            "groups:read",  # Read private channel metadata
            "groups:write",  # Manage private war-room channels
            "im:read",  # Read direct-message conversation metadata
            "mpim:read",  # Read multi-party DM metadata
            "reactions:write",  # Add emoji reactions to workflow messages
            "users:read",  # Look up Slack users for assignment/mentions
            "team:read",  # Read workspace/team metadata
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
    """Start Slack OAuth for the current tenant.

    Supports two modes:
    - Browser redirect (default): redirects to Slack authorize URL
    - JSON (Accept: application/json): returns {"redirect_url": "..."} for SPA usage
    """
    settings = get_settings()
    oauth = SlackOAuth()
    if not oauth.is_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack OAuth is not configured. Set SLACK_OAUTH_CLIENT_ID and SLACK_OAUTH_CLIENT_SECRET environment variables.",
        )

    state = secrets.token_urlsafe(32)
    redirect_uri = f"{settings.app_url}/api/integrations/oauth/slack/callback"

    await oauth_state_store.cleanup_expired()
    await oauth_state_store.save(
        provider="slack",
        state=state,
        tenant_id=str(auth.tenant_id),
        user_id=str(auth.user_id),
        redirect_uri=redirect_uri,
        return_to=return_to or f"{settings.app_url}/dashboard/onboarding-wizard",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )

    authorize_url = oauth.get_authorization_url(state, redirect_uri)

    # SPA mode: return JSON with the redirect URL so the frontend can navigate
    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return {"redirect_url": authorize_url}

    return RedirectResponse(url=authorize_url)


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

    state_data = await oauth_state_store.consume(provider="slack", state=state)
    logger.info("slack_oauth_callback_state", state_found=bool(state_data), state=state[:10])
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

    team_id = token.team.get("id") if token.team and isinstance(token.team, dict) else None
    if team_id:
        try:
            await oauth_token_store.upsert_token(
                tenant_id=state_data["tenant_id"],
                provider="slack",
                access_token=bot_token,
            )
            register_slack_team_mapping(team_id=team_id, tenant_id=state_data["tenant_id"])
        except Exception as e:
            logger.warning(
                "slack_oauth_token_store_upsert_failed",
                team_id=team_id,
                tenant_id=state_data["tenant_id"],
                error=str(e),
            )

    return RedirectResponse(url=f"{state_data['return_to']}?slack=connected")
