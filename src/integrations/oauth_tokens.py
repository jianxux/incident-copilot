"""OAuth token storage and refresh helpers for external integrations."""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import structlog

from ..db.supabase_db import get_db
from ..security import decrypt_str, encrypt_str
from ..supabase_client import is_supabase_db_enabled
from .oauth_providers import normalize_provider

logger = structlog.get_logger()


@dataclass
class IntegrationTokenRecord:
    """Decrypted integration token data used by application code."""

    id: str
    tenant_id: str
    provider: str
    access_token: str
    refresh_token: str | None
    token_expiry: datetime | None
    scopes: list[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class OAuthStateRecord:
    """State nonce payload for OAuth callback verification."""

    provider: str
    tenant_id: str
    user_id: str | None
    redirect_uri: str
    return_to: str
    created_at: datetime


class OAuthTokenStore:
    """Unified OAuth token and state storage.

    Uses Supabase when enabled; otherwise falls back to in-memory storage for local
    development and unit tests.
    """

    def __init__(self):
        self._state_lock = asyncio.Lock()
        self._states: dict[str, OAuthStateRecord] = {}
        self._tokens: dict[tuple[str, str], dict[str, Any]] = {}

    async def save_state(
        self,
        provider: str,
        tenant_id: str,
        user_id: str | None,
        redirect_uri: str,
        return_to: str,
    ) -> str:
        """Create and store OAuth state nonce."""
        state = secrets.token_urlsafe(32)
        rec = OAuthStateRecord(
            provider=normalize_provider(provider),
            tenant_id=tenant_id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            return_to=return_to,
            created_at=datetime.now(UTC),
        )
        async with self._state_lock:
            self._states[state] = rec
            self._gc_states_locked()
        return state

    async def pop_state(self, state: str) -> OAuthStateRecord | None:
        """Consume state nonce if it exists and is not expired."""
        async with self._state_lock:
            rec = self._states.pop(state, None)
            self._gc_states_locked()

        if not rec:
            return None

        if datetime.now(UTC) - rec.created_at > timedelta(minutes=15):
            return None

        return rec

    async def upsert_token(
        self,
        tenant_id: str,
        provider: str,
        access_token: str,
        refresh_token: str | None = None,
        token_expiry: datetime | None = None,
        scopes: list[str] | None = None,
    ) -> IntegrationTokenRecord:
        """Create/update encrypted token row."""
        provider = normalize_provider(provider)
        now = datetime.now(UTC)
        row = {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "provider": provider,
            "access_token": encrypt_str(access_token),
            "refresh_token": encrypt_str(refresh_token) if refresh_token else None,
            "token_expiry": token_expiry.isoformat() if token_expiry else None,
            "scopes": scopes or [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        if is_supabase_db_enabled():
            db = get_db(use_admin=True)
            persisted = await db.upsert_integration_token(
                tenant_id=tenant_id,
                provider=provider,
                access_token=row["access_token"],
                refresh_token=row["refresh_token"],
                token_expiry=row["token_expiry"],
                scopes=row["scopes"],
            )
            return self._to_record(persisted)

        key = (tenant_id, provider)
        existing = self._tokens.get(key)
        if existing:
            row["id"] = existing["id"]
            # Don't preserve old created_at — on reconnect, the date should reflect now
        self._tokens[key] = row
        return self._to_record(row)

    async def get_token(
        self,
        tenant_id: str,
        provider: str,
    ) -> IntegrationTokenRecord | None:
        """Get decrypted token row."""
        provider = normalize_provider(provider)
        if is_supabase_db_enabled():
            db = get_db(use_admin=True)
            row = await db.get_integration_token(tenant_id=tenant_id, provider=provider)
            if not row:
                return None
            return self._to_record(row)

        row = self._tokens.get((tenant_id, provider))
        return self._to_record(row) if row else None

    async def get_access_token(self, tenant_id: str, provider: str) -> str | None:
        """Get only access token for convenience."""
        rec = await self.get_token(tenant_id=tenant_id, provider=provider)
        return rec.access_token if rec else None

    async def delete_token(self, tenant_id: str, provider: str) -> bool:
        """Delete token row."""
        provider = normalize_provider(provider)
        if is_supabase_db_enabled():
            db = get_db(use_admin=True)
            return await db.delete_integration_token(tenant_id=tenant_id, provider=provider)

        self._tokens.pop((tenant_id, provider), None)
        return True

    async def list_expiring_tokens(
        self,
        refresh_window_minutes: int = 20,
    ) -> list[IntegrationTokenRecord]:
        """List tokens expiring within the refresh window."""
        cutoff = datetime.now(UTC) + timedelta(minutes=refresh_window_minutes)

        if is_supabase_db_enabled():
            db = get_db(use_admin=True)
            rows = await db.list_expiring_integration_tokens(
                expires_before=cutoff.isoformat(),
                limit=500,
            )
            return [
                rec
                for rec in (self._to_record(r) for r in rows)
                if rec and rec.refresh_token
            ]

        out: list[IntegrationTokenRecord] = []
        for row in self._tokens.values():
            rec = self._to_record(row)
            if not rec or not rec.refresh_token or not rec.token_expiry:
                continue
            if rec.token_expiry <= cutoff:
                out.append(rec)
        return out

    def _to_record(self, row: dict[str, Any] | None) -> IntegrationTokenRecord | None:
        if not row:
            return None

        try:
            access_token = decrypt_str(row["access_token"])
        except Exception:
            logger.error(
                "oauth_access_token_decrypt_failed",
                provider=row.get("provider"),
                tenant_id=row.get("tenant_id"),
            )
            return None

        refresh_token = None
        if row.get("refresh_token"):
            try:
                refresh_token = decrypt_str(row["refresh_token"])
            except Exception:
                logger.warning(
                    "oauth_refresh_token_decrypt_failed",
                    provider=row.get("provider"),
                    tenant_id=row.get("tenant_id"),
                )

        token_expiry = _parse_dt(row.get("token_expiry"))
        created_at = _parse_dt(row.get("created_at")) or datetime.now(UTC)
        updated_at = _parse_dt(row.get("updated_at")) or datetime.now(UTC)

        return IntegrationTokenRecord(
            id=str(row.get("id") or uuid4()),
            tenant_id=str(row.get("tenant_id")),
            provider=normalize_provider(str(row.get("provider"))),
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=token_expiry,
            scopes=list(row.get("scopes") or []),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _gc_states_locked(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(minutes=20)
        stale = [k for k, v in self._states.items() if v.created_at < cutoff]
        for key in stale:
            self._states.pop(key, None)



def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


oauth_token_store = OAuthTokenStore()
