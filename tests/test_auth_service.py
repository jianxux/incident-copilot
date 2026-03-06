from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.auth.models import PlanTier
from src.auth.service import AuthService


def _tenant_row(
    *,
    tenant_id: str = "tenant-1",
    name: str = "Acme",
    slug: str = "acme",
    plan: str = "free",
    integrations: dict | None = None,
) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "id": tenant_id,
        "name": name,
        "slug": slug,
        "plan": plan,
        "max_incidents_per_month": 50,
        "max_users": 3,
        "max_integrations": 3,
        "incidents_this_month": 0,
        "billing_cycle_start": now,
        "created_at": now,
        "updated_at": now,
        "integrations": integrations or {},
    }


@pytest.mark.asyncio
async def test_tenant_methods_use_in_memory_when_supabase_disabled(monkeypatch):
    monkeypatch.setattr("src.auth.service.is_supabase_db_enabled", lambda: False)
    service = AuthService()

    tenant = await service.create_tenant(name="Acme", slug="acme")
    assert tenant.slug == "acme"
    assert (await service.get_tenant(tenant.id)) is not None
    assert await service.get_tenant_by_slug("acme") is not None

    updated_plan = await service.update_tenant_plan(tenant.id, PlanTier.PRO)
    assert updated_plan.plan == PlanTier.PRO
    assert updated_plan.max_integrations == 10

    updated_integrations = await service.update_tenant_integrations(
        tenant.id,
        {"slack": {"bot_token": "xoxb-token"}},
    )
    assert updated_integrations.integrations["slack"]["bot_token"] == "xoxb-token"


@pytest.mark.asyncio
async def test_tenant_methods_use_supabase_when_enabled(monkeypatch):
    monkeypatch.setattr("src.auth.service.is_supabase_db_enabled", lambda: True)
    mock_db = AsyncMock()
    monkeypatch.setattr("src.auth.service.get_db", lambda **kwargs: mock_db)

    base = _tenant_row(plan="free", integrations={"pagerduty": {"api_key": "pd"}})
    created_row = {**base, "name": "Acme Inc", "slug": "acme-inc"}
    updated_integrations_row = {
        **created_row,
        "integrations": {
            "pagerduty": {"api_key": "pd"},
            "slack": {"bot_token": "xoxb-token"},
        },
    }
    updated_plan_row = {
        **updated_integrations_row,
        "plan": "pro",
        "max_incidents_per_month": 2000,
        "max_users": 50,
        "max_integrations": 10,
    }

    mock_db.get_tenant_by_slug = AsyncMock(return_value=None)
    mock_db.create_tenant = AsyncMock(return_value=created_row)
    mock_db.update_tenant = AsyncMock(
        side_effect=[updated_integrations_row, updated_plan_row]
    )

    service = AuthService()
    tenant = await service.create_tenant(name="Acme Inc", slug="acme-inc")
    assert tenant.id == "tenant-1"
    mock_db.create_tenant.assert_awaited_once()

    await service.update_tenant_integrations(
        "tenant-1", {"slack": {"bot_token": "xoxb-token"}}
    )
    mock_db.update_tenant.assert_any_await(
        "tenant-1",
        integrations={
            "pagerduty": {"api_key": "pd"},
            "slack": {"bot_token": "xoxb-token"},
        },
    )

    planned = await service.update_tenant_plan("tenant-1", PlanTier.PRO)
    assert planned.plan == PlanTier.PRO
    mock_db.update_tenant.assert_any_await(
        "tenant-1",
        plan="pro",
        max_incidents_per_month=2000,
        max_users=50,
        max_integrations=10,
    )


@pytest.mark.asyncio
async def test_get_tenant_is_read_through_cached_when_supabase_enabled(monkeypatch):
    monkeypatch.setattr("src.auth.service.is_supabase_db_enabled", lambda: True)
    mock_db = AsyncMock()
    mock_db.get_tenant = AsyncMock(return_value=_tenant_row())
    monkeypatch.setattr("src.auth.service.get_db", lambda **kwargs: mock_db)
    service = AuthService()

    first = await service.get_tenant("tenant-1")
    second = await service.get_tenant("tenant-1")

    assert first is not None
    assert second is not None
    assert first.id == second.id == "tenant-1"
    mock_db.get_tenant.assert_awaited_once_with("tenant-1")
