"""SQLite-backed onboarding checklist store."""

from __future__ import annotations

import os
from asyncio import Lock
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from .checklist import CHECKLIST_STEPS, OnboardingChecklist

logger = structlog.get_logger()

DEFAULT_DB_PATH = Path("data/onboarding.db")


class ChecklistStore:
    """SQLite-backed checklist store."""

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(
            db_path
            if db_path is not None
            else os.getenv("ONBOARDING_DB_PATH", str(DEFAULT_DB_PATH))
        )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_lock = Lock()
        self._initialized = False

    async def _init_db(self) -> None:
        """Initialize the database schema if needed."""
        async with self._init_lock:
            if self._initialized:
                return
            async with aiosqlite.connect(self._db_path) as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS onboarding_checklist (
                        tenant_id TEXT NOT NULL,
                        step TEXT NOT NULL,
                        done BOOLEAN NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (tenant_id, step)
                    )
                    """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_onboarding_checklist_tenant
                    ON onboarding_checklist(tenant_id)
                    """)
                await conn.commit()
            self._initialized = True
            logger.info("onboarding_checklist_db_initialized", path=str(self._db_path))

    async def _fetch_rows(self, tenant_id: str) -> list[dict[str, Any]]:
        await self._init_db()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT step, done, updated_at FROM onboarding_checklist WHERE tenant_id = ?",
                (tenant_id,),
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get(self, tenant_id: str) -> OnboardingChecklist:
        """Get the checklist for a tenant, creating defaults if missing."""
        rows = await self._fetch_rows(tenant_id)
        completed: dict[str, bool] = {r["step"]: bool(r["done"]) for r in rows}

        updated_at = None
        for row in rows:
            try:
                ts = datetime.fromisoformat(row["updated_at"])
            except (TypeError, ValueError):
                ts = None
            if ts and (updated_at is None or ts > updated_at):
                updated_at = ts

        checklist = OnboardingChecklist(
            tenant_id=tenant_id,
            completed=completed,
            updated_at=updated_at or datetime.now(UTC),
        )
        return checklist

    async def set_step(
        self, tenant_id: str, step: str, value: bool = True
    ) -> OnboardingChecklist:
        """Set a checklist step for a tenant."""
        if step not in CHECKLIST_STEPS:
            raise ValueError(f"Unknown onboarding step: {step}")

        await self._init_db()
        updated_at = datetime.now(UTC).isoformat()

        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO onboarding_checklist (tenant_id, step, done, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id, step) DO UPDATE SET
                    done = excluded.done,
                    updated_at = excluded.updated_at
                """,
                (tenant_id, step, bool(value), updated_at),
            )
            await conn.commit()

        logger.info(
            "onboarding_step_updated",
            tenant_id=tenant_id,
            step=step,
            value=value,
        )

        return await self.get(tenant_id)


async def migrate_onboarding_checklist(db_path: str | Path | None = None) -> None:
    """Create onboarding checklist table if it does not exist."""
    store = ChecklistStore(db_path=db_path)
    await store._init_db()


checklist_store = ChecklistStore()


class OAuthStateStore:
    """SQLite-backed OAuth state store for integration connect flows."""

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(
            db_path
            if db_path is not None
            else os.getenv("ONBOARDING_DB_PATH", str(DEFAULT_DB_PATH))
        )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_lock = Lock()
        self._initialized = False

    async def _init_db(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return
            async with aiosqlite.connect(self._db_path) as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS onboarding_oauth_states (
                        provider TEXT NOT NULL,
                        state TEXT NOT NULL,
                        tenant_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        redirect_uri TEXT NOT NULL,
                        return_to TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        PRIMARY KEY (provider, state)
                    )
                    """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_onboarding_oauth_states_expires_at
                    ON onboarding_oauth_states(expires_at)
                    """)
                await conn.commit()
            self._initialized = True
            logger.info(
                "onboarding_oauth_state_db_initialized", path=str(self._db_path)
            )

    async def save(
        self,
        *,
        provider: str,
        state: str,
        tenant_id: str,
        user_id: str,
        redirect_uri: str,
        return_to: str,
        expires_at: datetime,
    ) -> None:
        await self._init_db()
        created_at = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO onboarding_oauth_states (
                    provider, state, tenant_id, user_id, redirect_uri, return_to, created_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, state) DO UPDATE SET
                    tenant_id = excluded.tenant_id,
                    user_id = excluded.user_id,
                    redirect_uri = excluded.redirect_uri,
                    return_to = excluded.return_to,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (
                    provider,
                    state,
                    tenant_id,
                    user_id,
                    redirect_uri,
                    return_to,
                    created_at,
                    expires_at.isoformat(),
                ),
            )
            await conn.commit()

    async def consume(self, *, provider: str, state: str) -> dict[str, Any] | None:
        """Get-and-delete a valid state. Returns None if missing or expired."""
        await self._init_db()
        now = datetime.now(UTC)
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT provider, state, tenant_id, user_id, redirect_uri, return_to, created_at, expires_at
                FROM onboarding_oauth_states
                WHERE provider = ? AND state = ?
                """,
                (provider, state),
            )
            row = await cursor.fetchone()
            await conn.execute(
                "DELETE FROM onboarding_oauth_states WHERE provider = ? AND state = ?",
                (provider, state),
            )
            await conn.commit()

        if not row:
            return None

        payload = dict(row)
        try:
            expires_at = datetime.fromisoformat(payload["expires_at"])
        except (TypeError, ValueError):
            return None

        if expires_at < now:
            return None
        return payload

    async def cleanup_expired(self) -> int:
        await self._init_db()
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self._db_path) as conn:
            cursor = await conn.execute(
                "DELETE FROM onboarding_oauth_states WHERE expires_at < ?",
                (now,),
            )
            await conn.commit()
            count = cursor.rowcount or 0
        if count:
            logger.info("onboarding_oauth_states_cleaned", deleted=count)
        return count


class ServiceCatalogStore:
    """SQLite-backed tenant service catalog for onboarding."""

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(
            db_path
            if db_path is not None
            else os.getenv("ONBOARDING_DB_PATH", str(DEFAULT_DB_PATH))
        )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_lock = Lock()
        self._initialized = False

    async def _init_db(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return
            async with aiosqlite.connect(self._db_path) as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS onboarding_services (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tenant_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        source TEXT NOT NULL DEFAULT 'manual',
                        external_id TEXT,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        UNIQUE (tenant_id, name)
                    )
                    """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_onboarding_services_tenant
                    ON onboarding_services(tenant_id)
                    """)
                await conn.commit()
            self._initialized = True
            logger.info("onboarding_services_db_initialized", path=str(self._db_path))

    async def list(self, tenant_id: str) -> list[dict[str, Any]]:
        await self._init_db()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT id, tenant_id, name, source, external_id, metadata_json, created_at
                FROM onboarding_services
                WHERE tenant_id = ?
                ORDER BY name ASC
                """,
                (tenant_id,),
            )
            rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            try:
                import json

                d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
            except Exception:
                d["metadata"] = {}
                d.pop("metadata_json", None)
            result.append(d)
        return result

    async def upsert(
        self,
        *,
        tenant_id: str,
        name: str,
        source: str = "manual",
        external_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self._init_db()
        import json

        created_at = datetime.now(UTC).isoformat()
        metadata_json = json.dumps(
            metadata or {}, separators=(",", ":"), sort_keys=True
        )
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO onboarding_services (
                    tenant_id, name, source, external_id, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, name) DO UPDATE SET
                    source = excluded.source,
                    external_id = excluded.external_id,
                    metadata_json = excluded.metadata_json
                """,
                (tenant_id, name, source, external_id, metadata_json, created_at),
            )
            await conn.commit()

        rows = await self.list(tenant_id)
        for row in rows:
            if row["name"] == name:
                return row
        return {
            "tenant_id": tenant_id,
            "name": name,
            "source": source,
            "external_id": external_id,
            "metadata": metadata or {},
            "created_at": created_at,
        }

    async def delete(self, *, tenant_id: str, name: str) -> bool:
        await self._init_db()
        async with aiosqlite.connect(self._db_path) as conn:
            cursor = await conn.execute(
                "DELETE FROM onboarding_services WHERE tenant_id = ? AND name = ?",
                (tenant_id, name),
            )
            await conn.commit()
            return bool(cursor.rowcount)


oauth_state_store = OAuthStateStore()
service_catalog_store = ServiceCatalogStore()
