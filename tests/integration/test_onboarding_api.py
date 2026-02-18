"""Integration tests for onboarding and service catalog API endpoints.

These tests create a full FastAPI TestClient and require more memory.
Run separately: uv run pytest tests/integration/test_onboarding_api.py -v
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

os.environ["SUPABASE_DB_ENABLED"] = "false"
os.environ.pop("SUPABASE_URL", None)


@pytest.fixture(scope="module")
def app():
    from src.main import create_app
    return create_app()


@pytest.fixture(scope="module")
def authed_client(app, tmp_path_factory):
    from fastapi.testclient import TestClient
    from src.auth.middleware import AuthContext, get_auth_context
    from src.web.routes import require_dashboard_auth

    mock_tenant = MagicMock()
    mock_tenant.id = "test-tenant-id"
    mock_tenant.slug = "test-tenant"
    mock_tenant.integrations = {}

    async def override_auth():
        return AuthContext(
            user=MagicMock(id="user-1", email="test@test.com"),
            tenant=mock_tenant,
        )

    async def override_dashboard_auth():
        return {"tenant_id": "test-tenant-id", "user_id": "user-1"}

    app.dependency_overrides[get_auth_context] = override_auth
    app.dependency_overrides[require_dashboard_auth] = override_dashboard_auth

    tmp_path = tmp_path_factory.mktemp("onboarding")
    os.environ["ONBOARDING_DB_PATH"] = str(tmp_path / "onboarding.db")

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def anon_client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


def test_get_checklist(authed_client):
    resp = authed_client.get("/dashboard/api/onboarding/checklist")
    assert resp.status_code == 200
    data = resp.json()
    assert "steps" in data
    assert "progress" in data
    assert isinstance(data["steps"], list)
    assert len(data["steps"]) >= 6


def test_set_checklist_step(authed_client):
    resp = authed_client.post("/dashboard/api/onboarding/checklist/create_account")
    assert resp.status_code == 200
    steps = {s["id"]: s["done"] for s in resp.json()["steps"]}
    assert steps["create_account"] is True


def test_onboarding_status(authed_client):
    resp = authed_client.get("/dashboard/api/onboarding/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "integrations" in data
    assert "pagerduty" in data["integrations"]
    assert "slack" in data["integrations"]
    assert "details" in data


def test_test_integration_not_connected(authed_client):
    resp = authed_client.post("/dashboard/api/onboarding/test-integration/pagerduty")
    assert resp.status_code in (404, 500)


def test_service_api_list_empty(anon_client):
    resp = anon_client.get("/api/services")
    assert resp.status_code == 200
    assert resp.json() == []


def test_service_api_create(anon_client):
    resp = anon_client.post("/api/services", json={"name": "test-svc", "description": "Test"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "test-svc"


def test_service_api_missing_name(anon_client):
    resp = anon_client.post("/api/services", json={})
    assert resp.status_code == 422
