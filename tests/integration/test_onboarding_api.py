"""Integration tests for onboarding and service catalog API endpoints.

These tests create a full FastAPI TestClient and require more memory.
Run separately: uv run pytest tests/integration/test_onboarding_api.py -v
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock

import pytest

from src.integrations.oauth_tokens import oauth_token_store

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


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture(autouse=True)
def _reset_oauth_store():
    oauth_token_store._tokens.clear()
    oauth_token_store._states.clear()
    yield
    oauth_token_store._tokens.clear()
    oauth_token_store._states.clear()


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
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "not connected" in data["details"].lower()


def test_test_integration_pagerduty_stored_token_success(authed_client, monkeypatch):
    """Valid stored token should return ok:true with subdomain from /services."""

    class _Resp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    async def _unexpected_post(self, url, data=None, headers=None):
        raise AssertionError(f"unexpected POST call: {url}")

    async def _mock_get(self, url, headers=None):
        if "/services" in url:
            return _Resp(200, {
                "services": [{"html_url": "https://acme-corp.pagerduty.com/services/P123"}],
                "total": 1,
            })
        raise AssertionError(f"unexpected GET call: {url}")

    monkeypatch.setattr("httpx.AsyncClient.post", _unexpected_post)
    monkeypatch.setattr("httpx.AsyncClient.get", _mock_get)
    _run(
        oauth_token_store.upsert_token(
            tenant_id="test-tenant-id",
            provider="pagerduty",
            access_token="valid-token",
            refresh_token="refresh-token",
            scopes=["read", "write"],
        )
    )

    resp = authed_client.post("/dashboard/api/onboarding/test-integration/pagerduty")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert isinstance(data["details"], dict)
    assert data["details"]["subdomain"] == "acme-corp"
    assert data["details"]["scopes"] == ["read", "write"]
    assert data["details"]["connected_at"]


def test_test_integration_pagerduty_token_info_fails_gracefully(authed_client, monkeypatch):
    """If /services call fails, should still return ok:true without subdomain."""

    class _Resp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    async def _unexpected_post(self, url, data=None, headers=None):
        raise AssertionError(f"unexpected POST call: {url}")

    async def _mock_get(self, url, headers=None):
        if "/services" in url:
            return _Resp(403, {"error": {"message": "Forbidden"}})
        raise AssertionError(f"unexpected GET call: {url}")

    monkeypatch.setattr("httpx.AsyncClient.post", _unexpected_post)
    monkeypatch.setattr("httpx.AsyncClient.get", _mock_get)
    _run(
        oauth_token_store.upsert_token(
            tenant_id="test-tenant-id",
            provider="pagerduty",
            access_token="valid-token",
            refresh_token="refresh-token",
            scopes=["incidents.read"],
        )
    )

    resp = authed_client.post("/dashboard/api/onboarding/test-integration/pagerduty")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert isinstance(data["details"], dict)
    # subdomain should be None since token_info returned 401
    assert data["details"].get("subdomain") is None
    assert data["details"]["scopes"] == ["incidents.read"]


def test_test_integration_pagerduty_expired_refresh_failed(authed_client, monkeypatch):
    from datetime import UTC, datetime, timedelta

    monkeypatch.setenv("PAGERDUTY_CLIENT_ID", "pd-client")
    monkeypatch.setenv("PAGERDUTY_CLIENT_SECRET", "pd-secret")

    class _Resp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    async def _mock_post(self, url, data=None, headers=None):
        return _Resp(401, {"error": "invalid_grant"})

    monkeypatch.setattr("httpx.AsyncClient.post", _mock_post)
    _run(
        oauth_token_store.upsert_token(
            tenant_id="test-tenant-id",
            provider="pagerduty",
            access_token="expired-token",
            refresh_token="old-refresh-token",
            token_expiry=datetime.now(UTC) - timedelta(minutes=5),
        )
    )

    resp = authed_client.post("/dashboard/api/onboarding/test-integration/pagerduty")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "refresh failed" in data["details"].lower()


def test_test_integration_pagerduty_refresh_retries_inside_client_scope(authed_client, monkeypatch):
    from datetime import UTC, datetime, timedelta

    monkeypatch.setenv("PAGERDUTY_CLIENT_ID", "pd-client")
    monkeypatch.setenv("PAGERDUTY_CLIENT_SECRET", "pd-secret")

    class _Resp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class _ScopedAsyncClient:
        instances: list["_ScopedAsyncClient"] = []

        def __init__(self, timeout=10):
            self.timeout = timeout
            self.closed = False
            self.calls: list[tuple[str, str, dict | None]] = []
            _ScopedAsyncClient.instances.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self.closed = True

        async def get(self, url, headers=None):
            if self.closed:
                raise RuntimeError("client is closed")
            self.calls.append(("get", url, headers))
            return _Resp(500, {})

        async def post(self, url, data=None, headers=None):
            if self.closed:
                raise RuntimeError("client is closed")
            self.calls.append(("post", url, data))
            if url == "https://app.pagerduty.com/oauth/token":
                return _Resp(
                    200,
                    {
                        "access_token": "new-token",
                        "refresh_token": "new-refresh-token",
                        "expires_in": 3600,
                    },
                )
            return _Resp(500, {})

    monkeypatch.setattr("httpx.AsyncClient", _ScopedAsyncClient)
    _run(
        oauth_token_store.upsert_token(
            tenant_id="test-tenant-id",
            provider="pagerduty",
            access_token="old-token",
            refresh_token="old-refresh-token",
            token_expiry=datetime.now(UTC) - timedelta(minutes=5),
            scopes=["read"],
        )
    )

    resp = authed_client.post("/dashboard/api/onboarding/test-integration/pagerduty")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["details"]["refreshed_at"]

    stored = _run(oauth_token_store.get_token("test-tenant-id", "pagerduty"))
    assert stored is not None
    assert stored.access_token == "new-token"
    assert stored.refresh_token == "new-refresh-token"

    client = _ScopedAsyncClient.instances[-1]
    assert ("post", "https://app.pagerduty.com/oauth/token", {
        "grant_type": "refresh_token",
        "refresh_token": "old-refresh-token",
        "client_id": "pd-client",
        "client_secret": "pd-secret",
    }) in client.calls


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
