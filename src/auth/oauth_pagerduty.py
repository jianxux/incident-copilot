"""PagerDuty OAuth2 integration flow.

This is *not* user authentication. It's an integration connect flow that stores
PagerDuty OAuth tokens on the tenant for later API usage (and optional webhook
auto-configuration).

Docs:
- OAuth: https://developer.pagerduty.com/docs/ZG9jOjExMDI5NTU0-oauth
- Webhooks v3: https://developer.pagerduty.com/docs/ZG9jOjExMDI5NTU2-webhooks
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
from ..onboarding import oauth_state_store
from ..security import encrypt_json
from .middleware import AuthContext, get_auth_context, require_role
from .models import UserRole
from .service import auth_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/integrations/oauth/pagerduty", tags=["integrations"])


class PagerDutyToken(BaseModel):
    """PagerDuty OAuth token response (subset)."""

    access_token: str
    token_type: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None


class PagerDutyOAuth:
    AUTHORIZE_URL = "https://app.pagerduty.com/oauth/authorize"
    TOKEN_URL = "https://app.pagerduty.com/oauth/token"

    def __init__(self):
        settings = get_settings()
        self.client_id = getattr(settings, "pagerduty_oauth_client_id", "")
        self.client_secret = getattr(settings, "pagerduty_oauth_client_secret", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            # Scoped OAuth — must match scopes configured in PagerDuty App Registration.
            # Add these in PagerDuty UI: Services(Read), Incidents(Read), Users(Read), Webhooks(Read+Write)
            "scope": "openid services.read incidents.read users.read webhook_subscriptions.read webhook_subscriptions.write",
            "state": state,
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(
        self, code: str, redirect_uri: str
    ) -> PagerDutyToken | None:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                logger.error(
                    "pagerduty_oauth_token_error",
                    status=resp.status_code,
                    body=resp.text,
                )
                return None
            return PagerDutyToken(**resp.json())

    async def refresh(self, refresh_token: str) -> PagerDutyToken | None:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                logger.error(
                    "pagerduty_oauth_refresh_error",
                    status=resp.status_code,
                    body=resp.text,
                )
                return None
            return PagerDutyToken(**resp.json())


async def _create_or_update_webhook_subscription(
    access_token: str,
    webhook_url: str,
    signing_secret: str,
) -> str | None:
    """Create a webhook subscription in PagerDuty.

    Returns the subscription id if successful.

    NOTE: PagerDuty requires the integration to be configured for webhooks.
    """

    api_url = "https://api.pagerduty.com/webhook_subscriptions"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.pagerduty+json;version=2",
        "Content-Type": "application/json",
    }

    payload = {
        "webhook_subscription": {
            "type": "webhook_subscription",
            "description": "Incident Copilot webhook subscription",
            "delivery_method": {
                "type": "http_delivery_method",
                "url": webhook_url,
            },
            "events": ["incident.triggered"],
            "filter": {"type": "account_reference"},
            # PagerDuty uses a signing secret in the webhook signature header.
            "signing_secret": signing_secret,
        }
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(api_url, headers=headers, json=payload)
        if resp.status_code not in (200, 201):
            logger.error(
                "pagerduty_webhook_create_failed",
                status=resp.status_code,
                body=resp.text,
            )
            return None

        data = resp.json()
        ws = data.get("webhook_subscription") or {}
        return ws.get("id")


@router.get("/start")
@require_role(UserRole.OWNER, UserRole.ADMIN)
async def start_pagerduty_oauth(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    return_to: str | None = Query(default=None),
):
    """Start PagerDuty OAuth for the current tenant.

    Supports two modes:
    - Browser redirect (default): redirects to PagerDuty authorize URL
    - JSON (Accept: application/json): returns {"redirect_url": "..."} for SPA usage
    """
    settings = get_settings()
    oauth = PagerDutyOAuth()
    if not oauth.is_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PagerDuty OAuth is not configured. Set PAGERDUTY_OAUTH_CLIENT_ID and PAGERDUTY_OAUTH_CLIENT_SECRET environment variables.",
        )

    state = secrets.token_urlsafe(32)
    redirect_uri = f"{settings.app_url}/api/integrations/oauth/pagerduty/callback"

    # Best-effort cleanup so stale states do not accumulate.
    await oauth_state_store.cleanup_expired()
    await oauth_state_store.save(
        provider="pagerduty",
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
async def pagerduty_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """PagerDuty OAuth callback."""
    settings = get_settings()

    if error:
        logger.warning("pagerduty_oauth_denied", error=error)
        return RedirectResponse(
            url=f"{settings.app_url}/dashboard/onboarding-wizard?pd_error=denied"
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{settings.app_url}/dashboard/onboarding-wizard?pd_error=invalid"
        )

    state_data = await oauth_state_store.consume(provider="pagerduty", state=state)
    if not state_data:
        return RedirectResponse(
            url=f"{settings.app_url}/dashboard/onboarding-wizard?pd_error=state"
        )

    oauth = PagerDutyOAuth()
    token = await oauth.exchange_code(code, state_data["redirect_uri"])
    if not token:
        return RedirectResponse(
            url=f"{settings.app_url}/dashboard/onboarding-wizard?pd_error=token"
        )

    expires_at = None
    if token.expires_in:
        expires_at = datetime.now(UTC) + timedelta(seconds=token.expires_in)

    # Create webhook subscription + generate signing secret
    webhook_url = f"{settings.app_url}/webhooks/pagerduty"
    signing_secret = secrets.token_urlsafe(32)
    subscription_id = await _create_or_update_webhook_subscription(
        token.access_token, webhook_url, signing_secret
    )

    # Store encrypted token on tenant
    integration_record = {
        "oauth": {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "token_type": token.token_type,
        },
        "webhook": {
            "url": webhook_url,
            "subscription_id": subscription_id,
            "signing_secret": signing_secret,
        },
        "connected_at": datetime.now(UTC).isoformat(),
    }

    await auth_service.update_tenant_integrations(
        state_data["tenant_id"],
        {"pagerduty": {"encrypted": encrypt_json(integration_record)}},
    )

    # NOTE: existing PagerDutyAdapter reads signing secret from env settings.
    # This stored secret is for future multi-tenant support and auditing.

    return RedirectResponse(url=f"{state_data['return_to']}?pd=connected")
