from __future__ import annotations

from unittest.mock import MagicMock


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
