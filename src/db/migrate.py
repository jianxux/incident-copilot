"""Database migration runner for Supabase SQL files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import asyncpg
import structlog

from ..config import Settings, get_settings

logger = structlog.get_logger()

SCHEMA_MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class MigrationExecutor(Protocol):
    """Interface for applying and recording migrations."""

    async def ensure_schema_migrations_table(self) -> None: ...

    async def get_applied_migrations(self) -> set[str]: ...

    async def apply_sql(self, sql: str, filename: str) -> None: ...

    async def record_migration(self, filename: str) -> None: ...

    async def close(self) -> None: ...


class PostgresMigrationExecutor:
    """PostgreSQL-backed migration executor."""

    def __init__(self, database_url: str):
        dsn = database_url.replace("+asyncpg", "")
        self._dsn = dsn
        self._conn: asyncpg.Connection | None = None

    async def _conn_or_connect(self) -> asyncpg.Connection:
        if self._conn is None:
            self._conn = await asyncpg.connect(self._dsn)
        return self._conn

    async def ensure_schema_migrations_table(self) -> None:
        conn = await self._conn_or_connect()
        await conn.execute(SCHEMA_MIGRATIONS_TABLE_SQL)

    async def get_applied_migrations(self) -> set[str]:
        conn = await self._conn_or_connect()
        rows = await conn.fetch("SELECT filename FROM public.schema_migrations;")
        return {str(row["filename"]) for row in rows}

    async def apply_sql(self, sql: str, filename: str) -> None:
        conn = await self._conn_or_connect()
        async with conn.transaction():
            await conn.execute(sql)
            await conn.execute(
                """
                INSERT INTO public.schema_migrations (filename)
                VALUES ($1)
                ON CONFLICT (filename) DO NOTHING;
                """,
                filename,
            )

    async def record_migration(self, filename: str) -> None:
        conn = await self._conn_or_connect()
        await conn.execute(
            """
            INSERT INTO public.schema_migrations (filename)
            VALUES ($1)
            ON CONFLICT (filename) DO NOTHING;
            """,
            filename,
        )

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


@dataclass
class InMemoryMigrationExecutor:
    """In-memory executor used for tests and fallback behavior."""

    applied: set[str] = field(default_factory=set)
    applied_sql: list[str] = field(default_factory=list)
    ensured_table: bool = False

    async def ensure_schema_migrations_table(self) -> None:
        self.ensured_table = True

    async def get_applied_migrations(self) -> set[str]:
        return set(self.applied)

    async def apply_sql(self, sql: str, filename: str) -> None:
        self.applied_sql.append(filename)
        self.applied.add(filename)

    async def record_migration(self, filename: str) -> None:
        self.applied.add(filename)

    async def close(self) -> None:
        return None


def get_migration_files(migrations_dir: Path) -> list[Path]:
    """Get all SQL migration files sorted by filename."""
    if not migrations_dir.exists():
        return []
    return sorted(
        path for path in migrations_dir.iterdir() if path.is_file() and path.suffix == ".sql"
    )


def _default_migrations_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "supabase" / "migrations"


async def run_pending_migrations(
    *,
    migrations_dir: Path | None = None,
    executor: MigrationExecutor | None = None,
    settings: Settings | None = None,
) -> list[str]:
    """Apply pending SQL migrations in filename order.

    Returns:
        List of migration filenames that were applied during this run.
    """
    settings = settings or get_settings()
    migrations_dir = migrations_dir or _default_migrations_dir()
    files = get_migration_files(migrations_dir)

    if not files:
        logger.info("db_migrations_no_files", path=str(migrations_dir))
        return []

    created_executor = False
    if executor is None:
        if not settings.supabase_db_enabled:
            logger.info("db_migrations_skipped", reason="supabase_db_disabled")
            return []
        if "postgresql" not in settings.database_url:
            logger.info(
                "db_migrations_skipped",
                reason="non_postgres_database_url",
                database_url=settings.database_url,
            )
            return []
        executor = PostgresMigrationExecutor(settings.database_url)
        created_executor = True

    try:
        await executor.ensure_schema_migrations_table()
        applied = await executor.get_applied_migrations()
        newly_applied: list[str] = []

        for migration_file in files:
            filename = migration_file.name
            if filename in applied:
                continue

            sql = migration_file.read_text(encoding="utf-8").strip()
            if not sql:
                logger.warning("db_migration_empty_file", filename=filename)
                await executor.record_migration(filename)
                applied.add(filename)
                continue

            logger.info("db_migration_applying", filename=filename)
            await executor.apply_sql(sql, filename)
            applied.add(filename)
            newly_applied.append(filename)
            logger.info("db_migration_applied", filename=filename)

        logger.info(
            "db_migrations_complete",
            total_files=len(files),
            applied_count=len(newly_applied),
        )
        return newly_applied
    finally:
        if created_executor:
            await executor.close()
