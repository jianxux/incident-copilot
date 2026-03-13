"""OAuth integration connect/callback/status/disconnect endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from ..auth.middleware import AuthContext, get_auth_context, require_role
from ..auth.models import UserRole
from ..auth.service import auth_service
from ..config import get_settings
from ..integrations.oauth_providers import (
    get_provider_config,
    get_provider_credentials,
    normalize_provider,
)
from ..integrations.oauth_tokens import OAuthStateRecord, oauth_token_store

logger = structlog.get_logger()

router = APIRouter(prefix="/api/integrations", tags=["integrations-oauth"])


@router.get("/{provider}/connect")
@require_role(UserRole.OWNER, UserRole.ADMIN)
async def connect_provider(
    provider: str,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    return_to: str | None = Query(default=None),
):
    """Start OAuth connect flow for a provider and redirect to auth screen."""
    resolved = normalize_provider(provider)
    config = get_provider_config(resolved)
    client_id, client_secret = get_provider_credentials(resolved)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown provider: {provider}",
        )

    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"OAuth not configured for {resolved}. "
                f"Set {config.client_id_env} and {config.client_secret_env}."
            ),
        )

    settings = get_settings()
    # Some providers (PagerDuty) have legacy callback URLs registered in their OAuth app settings.
    # Map them to maintain compatibility.
    legacy_callback_map = {
        "pagerduty": f"{settings.app_url}/api/integrations/oauth/pagerduty/callback",
        "slack": f"{settings.app_url}/api/integrations/oauth/slack/callback",
    }
    redirect_uri = legacy_callback_map.get(
        resolved, f"{settings.app_url}/api/integrations/{resolved}/callback"
    )
    state = await oauth_token_store.save_state(
        provider=resolved,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        redirect_uri=redirect_uri,
        return_to=return_to or f"{settings.app_url}/settings",
    )

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }

    if resolved != "slack":
        params["response_type"] = "code"

    if config.default_scopes:
        delimiter = "," if resolved == "slack" else " "
        params["scope"] = delimiter.join(config.default_scopes)

    params.update(config.auth_params)

    authorize_url = f"{config.authorize_url}?{urlencode(params)}"

    if "application/json" in request.headers.get("accept", ""):
        return {"redirect_url": authorize_url}

    return RedirectResponse(url=authorize_url)


@router.get("/oauth/{provider}/callback")
async def callback_provider_legacy(
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Legacy callback path alias — delegates to generic handler."""
    return await callback_provider(
        provider=provider, code=code, state=state, error=error
    )


@router.get("/{provider}/callback")
async def callback_provider(
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Handle OAuth callback, exchange code, store encrypted tokens."""
    settings = get_settings()
    resolved = normalize_provider(provider)

    if error:
        return _redirect_result(
            base_url=f"{settings.app_url}/settings",
            provider=resolved,
            ok=False,
            reason=f"provider_error:{error}",
        )

    if not state or not code:
        return _redirect_result(
            base_url=f"{settings.app_url}/settings",
            provider=resolved,
            ok=False,
            reason="missing_code_or_state",
        )

    state_data = await oauth_token_store.pop_state(state)
    if not state_data:
        return _redirect_result(
            base_url=f"{settings.app_url}/settings",
            provider=resolved,
            ok=False,
            reason="invalid_or_expired_state",
        )

    if state_data.provider != resolved:
        return _redirect_result(
            base_url=state_data.return_to,
            provider=resolved,
            ok=False,
            reason="provider_mismatch",
        )

    try:
        token_data = await _exchange_code_for_token(
            provider=resolved,
            code=code,
            state_data=state_data,
        )
    except HTTPException as e:
        return _redirect_result(
            base_url=state_data.return_to,
            provider=resolved,
            ok=False,
            reason=str(e.detail),
        )

    expires_in = token_data.get("expires_in")
    expiry = None
    if isinstance(expires_in, int) and expires_in > 0:
        expiry = datetime.now(UTC) + timedelta(seconds=expires_in)

    scopes = _parse_scopes(token_data.get("scope"), resolved)

    import sys

    print(
        f"DEBUG_OAUTH: pre_upsert provider={resolved} tenant={state_data.tenant_id}",
        flush=True,
        file=sys.stderr,
    )

    try:
        await oauth_token_store.upsert_token(
            tenant_id=state_data.tenant_id,
            provider=resolved,
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_expiry=expiry,
            scopes=scopes,
        )
        print(f"DEBUG_OAUTH: upsert_token OK", flush=True, file=sys.stderr)
    except Exception as e:
        print(f"DEBUG_OAUTH: upsert_token FAILED: {e}", flush=True, file=sys.stderr)

    # Slack-specific: store integration record + register team mapping
    print(
        f"DEBUG_OAUTH: entering slack block, resolved={resolved}",
        flush=True,
        file=sys.stderr,
    )
    if resolved == "slack":
        team = token_data.get("team")
        team_id_str = team.get("id") if isinstance(team, dict) else None
        if team_id_str:
            from ..integrations.slack_lifecycle import register_slack_team_mapping

            register_slack_team_mapping(
                team_id=team_id_str, tenant_id=state_data.tenant_id
            )

        from ..security import encrypt_json

        authed_user = token_data.get("authed_user")
        authed_user_token = (
            authed_user.get("access_token") if isinstance(authed_user, dict) else None
        )
        integration_record = {
            "oauth": {
                "bot_token": token_data["access_token"],
                "authed_user_token": authed_user_token,
                "scope": token_data.get("scope"),
                "team": team,
                "bot_user_id": token_data.get("bot_user_id"),
                "app_id": token_data.get("app_id"),
            },
            "connected_at": datetime.now(UTC).isoformat(),
        }
        try:
            await auth_service.update_tenant_integrations(
                state_data.tenant_id,
                {"slack": {"encrypted": encrypt_json(integration_record)}},
            )
            print(
                f"DEBUG_OAUTH: tenant_integrations SAVED team={team_id_str}",
                flush=True,
                file=sys.stderr,
            )
        except Exception as e:
            print(
                f"DEBUG_OAUTH: tenant_integrations FAILED: {e}",
                flush=True,
                file=sys.stderr,
            )

    # Update onboarding checklist if applicable
    checklist_map = {
        "pagerduty": "connect_alerting",
        "slack": "connect_slack",
        "github": "connect_github",
        "datadog": "connect_datadog",
    }
    checklist_step = checklist_map.get(resolved)
    if checklist_step:
        try:
            from ..onboarding import checklist_store

            await checklist_store.set_step(state_data.tenant_id, checklist_step, True)
        except Exception:
            logger.warning("checklist_update_failed", provider=resolved)

    return _redirect_result(
        base_url=state_data.return_to,
        provider=resolved,
        ok=True,
        reason="connected",
    )


@router.get("/{provider}/status")
async def provider_status(
    provider: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Get OAuth connection status for current tenant."""
    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    resolved = normalize_provider(provider)
    config = get_provider_config(resolved)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown provider: {provider}",
        )

    token = await oauth_token_store.get_token(auth.tenant_id, resolved)
    return {
        "provider": resolved,
        "connected": bool(token),
        "token_expiry": (
            token.token_expiry.isoformat() if token and token.token_expiry else None
        ),
        "scopes": token.scopes if token else [],
    }


@router.delete("/{provider}/disconnect")
@require_role(UserRole.OWNER, UserRole.ADMIN)
async def provider_disconnect(
    provider: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Disconnect OAuth integration and remove stored token."""
    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    resolved = normalize_provider(provider)
    token = await oauth_token_store.get_token(auth.tenant_id, resolved)

    revoked = False
    revoke_error = None
    if token:
        try:
            revoked = await _revoke_token(resolved, token.access_token)
        except Exception as e:
            revoke_error = str(e)

    await oauth_token_store.delete_token(auth.tenant_id, resolved)

    return {
        "provider": resolved,
        "disconnected": True,
        "revoked": revoked,
        "revoke_error": revoke_error,
    }


@router.post("/{provider}/test")
async def provider_test(
    provider: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Test OAuth integration connectivity for current tenant."""
    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    resolved = normalize_provider(provider)
    config = get_provider_config(resolved)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown provider: {provider}",
        )

    token = await oauth_token_store.get_token(auth.tenant_id, resolved)
    if not token or not token.access_token:
        return {
            "provider": resolved,
            "ok": False,
            "details": "Integration is not connected",
        }

    if resolved == "pagerduty":
        details = {
            "subdomain": None,
            "scopes": token.scopes,
            "connected_at": token.created_at.isoformat() if token.created_at else None,
        }
        details.update(await _load_pagerduty_stored_details(auth.tenant_id))

        now = datetime.now(UTC)
        if not token.token_expiry or token.token_expiry > now:
            return {
                "provider": resolved,
                "ok": True,
                "details": details,
            }

        refreshed = await _refresh_provider_token(auth.tenant_id, resolved, token)
        if refreshed:
            refreshed_details = {
                "subdomain": details.get("subdomain"),
                "scopes": refreshed.scopes,
                "connected_at": details.get("connected_at")
                or (refreshed.created_at.isoformat() if refreshed.created_at else None),
                "refreshed_at": datetime.now(UTC).isoformat(),
            }
            return {
                "provider": resolved,
                "ok": True,
                "details": refreshed_details,
            }

        return {
            "provider": resolved,
            "ok": False,
            "details": "PagerDuty token is expired and refresh failed",
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if resolved == "slack":
                resp = await client.post(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {token.access_token}"},
                )
                data = resp.json() if resp.content else {}
                if data.get("ok"):
                    return {
                        "provider": resolved,
                        "ok": True,
                        "details": "Slack API reachable",
                    }
                return {
                    "provider": resolved,
                    "ok": False,
                    "details": f"Slack auth failed: {data.get('error', 'unknown')}",
                }

            if resolved == "github":
                resp = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"Bearer {token.access_token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                if resp.status_code == 200:
                    return {
                        "provider": resolved,
                        "ok": True,
                        "details": "GitHub API reachable",
                    }
                return {
                    "provider": resolved,
                    "ok": False,
                    "details": f"GitHub API returned {resp.status_code}",
                }

            if resolved == "datadog":
                return {
                    "provider": resolved,
                    "ok": True,
                    "details": "Datadog token stored",
                }
    except Exception as e:
        logger.warning(
            "integration_test_failed",
            provider=resolved,
            tenant_id=auth.tenant_id,
            error=str(e),
        )
        return {
            "provider": resolved,
            "ok": False,
            "details": f"Connection test failed: {type(e).__name__}",
        }

    return {
        "provider": resolved,
        "ok": False,
        "details": "Unsupported integration provider for test",
    }


async def _load_pagerduty_stored_details(tenant_id: str) -> dict:
    """Best-effort retrieval of PagerDuty metadata stored in legacy configs."""
    try:
        from ..db.supabase_db import get_db
        from ..security.crypto import decrypt_json

        db = get_db(use_admin=True)
        rows = (
            db.client.table("integration_configs")
            .select("config")
            .eq("tenant_id", tenant_id)
            .eq("type", "pagerduty")
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if not rows.data:
            return {}

        config = rows.data[0].get("config", {})
        encrypted = config.get("encrypted", "") if isinstance(config, dict) else ""
        if not encrypted:
            return {}

        decrypted = decrypt_json(encrypted)
        oauth = decrypted.get("oauth", {}) if isinstance(decrypted, dict) else {}
        scopes = oauth.get("scope")
        if isinstance(scopes, str):
            scopes = [
                s.strip() for s in scopes.replace(",", " ").split(" ") if s.strip()
            ]
        elif not isinstance(scopes, list):
            scopes = None
        return {
            "subdomain": decrypted.get("subdomain"),
            "scopes": scopes,
            "connected_at": decrypted.get("connected_at"),
        }
    except Exception:
        return {}


async def _refresh_provider_token(
    tenant_id: str,
    provider: str,
    token,
):
    """Attempt OAuth refresh and persist new credentials."""
    if not token.refresh_token:
        return None

    config = get_provider_config(provider)
    client_id, client_secret = get_provider_credentials(provider)
    if not config or not client_id or not client_secret:
        return None

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": token.refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                config.token_url,
                data=payload,
                headers={"Accept": "application/json"},
            )
    except Exception:
        return None

    if response.status_code != 200:
        return None

    body = response.json()
    access_token = body.get("access_token")
    if not access_token:
        return None

    expires_in = body.get("expires_in")
    expiry = None
    try:
        expires_in_value = int(expires_in) if expires_in is not None else None
    except (TypeError, ValueError):
        expires_in_value = None
    if expires_in_value and expires_in_value > 0:
        expiry = datetime.now(UTC) + timedelta(seconds=expires_in_value)

    scopes_raw = body.get("scope")
    if isinstance(scopes_raw, str):
        scopes = _parse_scopes(scopes_raw, provider)
    else:
        scopes = token.scopes

    return await oauth_token_store.upsert_token(
        tenant_id=tenant_id,
        provider=provider,
        access_token=access_token,
        refresh_token=body.get("refresh_token") or token.refresh_token,
        token_expiry=expiry,
        scopes=scopes,
    )


async def _exchange_code_for_token(
    provider: str,
    code: str,
    state_data: OAuthStateRecord,
) -> dict:
    config = get_provider_config(provider)
    client_id, client_secret = get_provider_credentials(provider)

    if not config or not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="oauth_not_configured",
        )

    payload = {
        "code": code,
        "redirect_uri": state_data.redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    if provider != "slack":
        payload["grant_type"] = "authorization_code"

    headers = {"Accept": "application/json"}

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(config.token_url, data=payload, headers=headers)

    if response.status_code != 200:
        logger.warning(
            "oauth_token_exchange_http_error",
            provider=provider,
            status=response.status_code,
            body=response.text[:250],
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="token_exchange_failed",
        )

    body = response.json()

    if provider == "slack":
        if not body.get("ok") or not body.get("access_token"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"slack_token_error:{body.get('error', 'unknown')}",
            )

        return {
            "access_token": body.get("access_token"),
            "refresh_token": body.get("refresh_token"),
            "expires_in": body.get("expires_in"),
            "scope": body.get("scope"),
        }

    if not body.get("access_token"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="missing_access_token",
        )

    return body


async def _revoke_token(provider: str, access_token: str) -> bool:
    config = get_provider_config(provider)
    client_id, client_secret = get_provider_credentials(provider)

    if not config or not config.revoke_url:
        return False

    payload = {"token": access_token}
    if client_id:
        payload["client_id"] = client_id
    if client_secret:
        payload["client_secret"] = client_secret

    headers = {"Accept": "application/json"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(config.revoke_url, data=payload, headers=headers)

    # Some providers return 200 with body, some 204 no content.
    return response.status_code in (200, 201, 202, 204)


def _parse_scopes(scope: str | None, provider: str) -> list[str]:
    if not scope:
        config = get_provider_config(provider)
        return config.default_scopes if config else []

    if "," in scope:
        return [s.strip() for s in scope.split(",") if s.strip()]

    return [s.strip() for s in scope.split(" ") if s.strip()]


def _redirect_result(base_url: str, provider: str, ok: bool, reason: str):
    join = "&" if "?" in base_url else "?"
    url = f"{base_url}{join}oauth_provider={provider}&oauth_result={'success' if ok else 'error'}&oauth_reason={reason}"
    return RedirectResponse(url=url)
