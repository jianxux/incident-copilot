from pathlib import Path

import pytest

from src.config import Settings
from src.db.migrate import InMemoryMigrationExecutor, run_pending_migrations


def test_tenants_missing_columns_migration_has_idempotent_add_column_statements():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "migrations"
        / "20260302000001_add_tenants_missing_columns.sql"
    )
    assert migration_path.exists()

    sql = migration_path.read_text(encoding="utf-8")
    required_columns = [
        "integrations",
        "max_incidents_per_month",
        "max_users",
        "max_integrations",
        "incidents_this_month",
        "billing_cycle_start",
    ]
    for column in required_columns:
        assert f"ADD COLUMN IF NOT EXISTS {column}" in sql

    assert "ALTER TABLE IF EXISTS public.tenants" in sql


@pytest.mark.asyncio
async def test_run_pending_migrations_orders_files_and_skips_previously_applied(tmp_path: Path):
    first = tmp_path / "20260101000001_first.sql"
    second = tmp_path / "20260101000002_second.sql"
    third = tmp_path / "20260101000003_third.sql"
    first.write_text("SELECT 1;", encoding="utf-8")
    second.write_text("SELECT 2;", encoding="utf-8")
    third.write_text("SELECT 3;", encoding="utf-8")

    executor = InMemoryMigrationExecutor(applied={"20260101000002_second.sql"})
    settings = Settings(
        supabase_db_enabled=True,
        supabase_url="https://example.supabase.co",
        supabase_anon_key="anon",
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/test",
    )

    applied = await run_pending_migrations(
        migrations_dir=tmp_path,
        executor=executor,
        settings=settings,
    )

    assert executor.ensured_table is True
    assert applied == ["20260101000001_first.sql", "20260101000003_third.sql"]
    assert executor.applied_sql == ["20260101000001_first.sql", "20260101000003_third.sql"]


@pytest.mark.asyncio
async def test_run_pending_migrations_uses_in_memory_fallback_executor(tmp_path: Path):
    migration = tmp_path / "20260101000001_sample.sql"
    migration.write_text("SELECT 1;", encoding="utf-8")

    executor = InMemoryMigrationExecutor()
    settings = Settings(
        supabase_db_enabled=False,
        database_url="sqlite:///./test.db",
    )

    applied = await run_pending_migrations(
        migrations_dir=tmp_path,
        executor=executor,
        settings=settings,
    )

    assert applied == ["20260101000001_sample.sql"]
    assert executor.applied_sql == ["20260101000001_sample.sql"]
