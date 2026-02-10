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
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS onboarding_checklist (
                        tenant_id TEXT NOT NULL,
                        step TEXT NOT NULL,
                        done BOOLEAN NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (tenant_id, step)
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_onboarding_checklist_tenant
                    ON onboarding_checklist(tenant_id)
                    """
                )
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
