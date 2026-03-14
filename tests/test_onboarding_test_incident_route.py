from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def test_onboarding_test_incident_missing_tenant_returns_401():
    from fastapi.testclient import TestClient

    from src.auth.middleware import AuthContext, get_auth_context
    from src.main import create_app
    from src.web.routes import require_dashboard_auth

    app = create_app()

    async def override_auth():
        return AuthContext(user=MagicMock(id="u1"), tenant=None)

    async def override_dashboard_auth():
        return {"tenant_id": "fallback", "user_id": "u1"}

    app.dependency_overrides[get_auth_context] = override_auth
    app.dependency_overrides[require_dashboard_auth] = override_dashboard_auth

    with TestClient(app) as client:
        response = client.post("/dashboard/api/onboarding/test-incident")

    app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["detail"] == "auth_required"


def test_onboarding_test_incident_status_missing_tenant_returns_401():
    from fastapi.testclient import TestClient

    from src.auth.middleware import AuthContext, get_auth_context
    from src.main import create_app
    from src.web.routes import require_dashboard_auth

    app = create_app()

    async def override_auth():
        return AuthContext(user=MagicMock(id="u1"), tenant=None)

    async def override_dashboard_auth():
        return {"tenant_id": "fallback", "user_id": "u1"}

    app.dependency_overrides[get_auth_context] = override_auth
    app.dependency_overrides[require_dashboard_auth] = override_dashboard_auth

    with TestClient(app) as client:
        response = client.get("/dashboard/api/onboarding/test-incident/inc-1")

    app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["detail"] == "auth_required"


@pytest.mark.asyncio
async def test_get_test_incident_status_filters_by_tenant_id(monkeypatch):
    from src.auth.middleware import AuthContext
    from src.web.routes.onboarding import get_test_incident_status

    eq_calls: list[tuple[str, str]] = []

    class _FakeQuery:
        def select(self, _fields):
            return self

        def eq(self, field, value):
            eq_calls.append((field, value))
            return self

        def limit(self, _limit):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    fake_db = SimpleNamespace(client=SimpleNamespace(table=lambda _name: _FakeQuery()))
    monkeypatch.setattr("src.db.supabase_db.get_db", lambda use_admin=True: fake_db)

    store_get_incident = AsyncMock(
        return_value=SimpleNamespace(title="Stored title", status="processing")
    )
    monkeypatch.setattr("src.web.store.incident_store.get_incident", store_get_incident)

    tenant = MagicMock()
    tenant.id = "tenant-123"

    result = await get_test_incident_status(
        "inc-tenant-scope",
        auth=AuthContext(user=MagicMock(id="u1"), tenant=tenant),
    )

    assert ("id", "inc-tenant-scope") in eq_calls
    assert ("tenant_id", "tenant-123") in eq_calls
    store_get_incident.assert_awaited_once_with(
        "inc-tenant-scope", tenant_id="tenant-123"
    )
    assert result["status"] == "processing"
