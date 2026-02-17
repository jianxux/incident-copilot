"""Background refresh of expiring OAuth integration tokens."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from .oauth_providers import get_provider_config, get_provider_credentials
from .oauth_tokens import oauth_token_store

logger = structlog.get_logger()

_refresh_task: asyncio.Task | None = None
_stop_event = asyncio.Event()


async def refresh_expiring_tokens(refresh_window_minutes: int = 20) -> int:
    """Refresh tokens expiring within the configured window.

    Returns number of tokens refreshed successfully.
    """
    tokens = await oauth_token_store.list_expiring_tokens(
        refresh_window_minutes=refresh_window_minutes
    )
    refreshed = 0

    for token in tokens:
        if not token.refresh_token:
            continue

        config = get_provider_config(token.provider)
        client_id, client_secret = get_provider_credentials(token.provider)
        if not config or not client_id or not client_secret:
            continue

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

            if response.status_code != 200:
                logger.warning(
                    "oauth_token_refresh_failed",
                    provider=token.provider,
                    tenant_id=token.tenant_id,
                    status=response.status_code,
                )
                continue

            body = response.json()
            access_token = body.get("access_token")
            if not access_token:
                logger.warning(
                    "oauth_token_refresh_missing_access_token",
                    provider=token.provider,
                    tenant_id=token.tenant_id,
                )
                continue

            expires_in = body.get("expires_in")
            expiry = None
            if isinstance(expires_in, int) and expires_in > 0:
                expiry = datetime.now(UTC) + timedelta(seconds=expires_in)

            scopes_raw = body.get("scope")
            if isinstance(scopes_raw, str):
                scopes = [s for s in scopes_raw.replace(",", " ").split(" ") if s]
            else:
                scopes = token.scopes

            await oauth_token_store.upsert_token(
                tenant_id=token.tenant_id,
                provider=token.provider,
                access_token=access_token,
                refresh_token=body.get("refresh_token") or token.refresh_token,
                token_expiry=expiry,
                scopes=scopes,
            )
            refreshed += 1

        except Exception as e:
            logger.warning(
                "oauth_token_refresh_exception",
                provider=token.provider,
                tenant_id=token.tenant_id,
                error=str(e),
            )

    return refreshed


async def _refresh_loop(interval_seconds: int) -> None:
    while not _stop_event.is_set():
        try:
            count = await refresh_expiring_tokens()
            if count:
                logger.info("oauth_tokens_refreshed", count=count)
        except Exception as e:
            logger.warning("oauth_refresh_loop_failed", error=str(e))

        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue


async def start_oauth_refresh_worker(interval_seconds: int = 300) -> None:
    """Start periodic OAuth token refresh worker."""
    global _refresh_task
    if _refresh_task and not _refresh_task.done():
        return

    _stop_event.clear()
    _refresh_task = asyncio.create_task(_refresh_loop(interval_seconds))


async def stop_oauth_refresh_worker() -> None:
    """Stop periodic OAuth token refresh worker."""
    global _refresh_task
    if not _refresh_task:
        return

    _stop_event.set()
    _refresh_task.cancel()
    try:
        await _refresh_task
    except asyncio.CancelledError:
        pass
    finally:
        _refresh_task = None
