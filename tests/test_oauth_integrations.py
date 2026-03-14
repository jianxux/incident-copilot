"""Tests for OAuth integration routes."""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from src.auth.models import UserRole
from src.auth.service import auth_service
from src.integrations.oauth_tokens import oauth_token_store
from src.main import create_app


class _DummyResponse:
    def __init__(self, status_code: int, payload: dict, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def _create_headers() -> dict[str, str]:
    headers, _ = await _create_headers_and_tenant()
    return headers


async def _create_headers_and_tenant() -> tuple[dict[str, str], str]:
    tenant = await auth_service.create_tenant(
        name="OAuth Tenant",
        slug=f"oauth-test-{asyncio.get_running_loop().time()}".replace(".", "-"),
    )
    user = await auth_service.create_user(
        email=f"owner-{tenant.id}@example.com",
        name="Owner",
        tenant_id=tenant.id,
        role=UserRole.OWNER,
    )
    session = await auth_service.create_session(user.id)
    return {"Authorization": f"Bearer {session.access_token}"}, tenant.id


@pytest.fixture(autouse=True)
def _reset_oauth_store():
    oauth_token_store._tokens.clear()
    oauth_token_store._states.clear()
    yield
    oauth_token_store._tokens.clear()
    oauth_token_store._states.clear()


@pytest.mark.unit
def test_slack_oauth_connect_callback_status_disconnect(monkeypatch):
    monkeypatch.setenv("SLACK_CLIENT_ID", "client-id")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "client-secret")

    async def _mock_post(self, url, data=None, headers=None):
        if "oauth.v2.access" in url:
            return _DummyResponse(
                200,
                {
                    "ok": True,
                    "access_token": "xoxb-test-token",
                    "refresh_token": "refresh-token",
                    "expires_in": 3600,
                    "scope": "channels:read,chat:write,users:read,team:read",
                },
            )
        if "auth.revoke" in url:
            return _DummyResponse(200, {"ok": True})
        return _DummyResponse(404, {}, text="not-found")

    monkeypatch.setattr("src.api.oauth_integrations.httpx.AsyncClient.post", _mock_post)

    app = create_app()
    client = TestClient(app)
    headers = _run(_create_headers())

    connect = client.get(
        "/api/integrations/slack/connect", headers=headers, follow_redirects=False
    )
    assert connect.status_code in (302, 307)
    parsed = urlparse(connect.headers["location"])
    params = parse_qs(parsed.query)
    state = params["state"][0]

    callback = client.get(
        f"/api/integrations/slack/callback?code=test-code&state={state}",
        follow_redirects=False,
    )
    assert callback.status_code in (302, 307)
    assert "oauth_result=success" in callback.headers["location"]

    status_connected = client.get("/api/integrations/slack/status", headers=headers)
    assert status_connected.status_code == 200
    assert status_connected.json()["connected"] is True

    disconnect = client.delete("/api/integrations/slack/disconnect", headers=headers)
    assert disconnect.status_code == 200
    assert disconnect.json()["disconnected"] is True

    status_disconnected = client.get("/api/integrations/slack/status", headers=headers)
    assert status_disconnected.status_code == 200
    assert status_disconnected.json()["connected"] is False


@pytest.mark.unit
def test_oauth_callback_rejects_invalid_state(monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "gh-client")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "gh-secret")

    app = create_app()
    client = TestClient(app)

    response = client.get(
        "/api/integrations/github/callback?code=abc&state=missing-state",
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "oauth_result=error" in response.headers["location"]
    assert "invalid_or_expired_state" in response.headers["location"]


@pytest.mark.unit
def test_provider_test_returns_structured_result_when_disconnected():
    app = create_app()
    client = TestClient(app)
    headers = _run(_create_headers())

    response = client.post("/api/integrations/slack/test", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "slack"
    assert data["ok"] is False
    assert isinstance(data["details"], str)


@pytest.mark.unit
def test_provider_test_slack_success(monkeypatch):
    class _SlackResponse:
        status_code = 200
        content = b'{"ok": true}'

        @staticmethod
        def json():
            return {"ok": True}

    async def _mock_post(self, url, data=None, headers=None):
        if "oauth.v2.access" in url:
            return _DummyResponse(
                200,
                {
                    "ok": True,
                    "access_token": "xoxb-test-token",
                    "refresh_token": "refresh-token",
                    "expires_in": 3600,
                    "scope": "channels:read",
                },
            )
        return _SlackResponse()

    monkeypatch.setenv("SLACK_CLIENT_ID", "client-id")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr("src.api.oauth_integrations.httpx.AsyncClient.post", _mock_post)

    app = create_app()
    client = TestClient(app)
    headers = _run(_create_headers())

    connect = client.get(
        "/api/integrations/slack/connect", headers=headers, follow_redirects=False
    )
    parsed = urlparse(connect.headers["location"])
    state = parse_qs(parsed.query)["state"][0]
    client.get(
        f"/api/integrations/slack/callback?code=test-code&state={state}",
        follow_redirects=False,
    )

    response = client.post("/api/integrations/slack/test", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert isinstance(data["details"], str)


@pytest.mark.unit
def test_provider_test_pagerduty_uses_stored_token_without_api_calls(monkeypatch):
    async def _unexpected_post(self, url, data=None, headers=None):
        raise AssertionError(f"unexpected network call: {url}")

    monkeypatch.setattr(
        "src.api.oauth_integrations.httpx.AsyncClient.post", _unexpected_post
    )
    app = create_app()
    client = TestClient(app)
    headers, tenant_id = _run(_create_headers_and_tenant())
    _run(
        oauth_token_store.upsert_token(
            tenant_id=tenant_id,
            provider="pagerduty",
            access_token="pd-access-token",
            scopes=["read", "write"],
        )
    )

    response = client.post("/api/integrations/pagerduty/test", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "pagerduty"
    assert data["ok"] is True
    assert data["details"]["scopes"] == ["read", "write"]
    assert data["details"]["connected_at"]


@pytest.mark.unit
def test_provider_test_pagerduty_expired_refresh_success(monkeypatch):
    from datetime import UTC, datetime, timedelta

    monkeypatch.setenv("PAGERDUTY_CLIENT_ID", "pd-client")
    monkeypatch.setenv("PAGERDUTY_CLIENT_SECRET", "pd-secret")
    seen_urls: list[str] = []

    async def _mock_post(self, url, data=None, headers=None):
        seen_urls.append(url)
        if url == "https://identity.pagerduty.com/oauth/token":
            return _DummyResponse(
                200,
                {
                    "access_token": "new-access-token",
                    "refresh_token": "new-refresh-token",
                    "expires_in": 3600,
                    "scope": "read write",
                },
            )
        return _DummyResponse(500, {})

    monkeypatch.setattr("src.api.oauth_integrations.httpx.AsyncClient.post", _mock_post)
    app = create_app()
    client = TestClient(app)
    headers, tenant_id = _run(_create_headers_and_tenant())
    _run(
        oauth_token_store.upsert_token(
            tenant_id=tenant_id,
            provider="pagerduty",
            access_token="expired-access-token",
            refresh_token="old-refresh-token",
            token_expiry=datetime.now(UTC) - timedelta(minutes=1),
        )
    )

    response = client.post("/api/integrations/pagerduty/test", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "pagerduty"
    assert data["ok"] is True
    assert data["details"]["refreshed_at"]
    assert "https://identity.pagerduty.com/oauth/token" in seen_urls

    stored = _run(oauth_token_store.get_token(tenant_id, "pagerduty"))
    assert stored is not None
    assert stored.access_token == "new-access-token"
    assert stored.refresh_token == "new-refresh-token"


@pytest.mark.unit
def test_provider_test_pagerduty_expired_refresh_failed(monkeypatch):
    from datetime import UTC, datetime, timedelta

    monkeypatch.setenv("PAGERDUTY_CLIENT_ID", "pd-client")
    monkeypatch.setenv("PAGERDUTY_CLIENT_SECRET", "pd-secret")

    async def _mock_post(self, url, data=None, headers=None):
        return _DummyResponse(401, {"error": "invalid_grant"})

    monkeypatch.setattr("src.api.oauth_integrations.httpx.AsyncClient.post", _mock_post)

    app = create_app()
    client = TestClient(app)
    headers, tenant_id = _run(_create_headers_and_tenant())
    _run(
        oauth_token_store.upsert_token(
            tenant_id=tenant_id,
            provider="pagerduty",
            access_token="expired-access-token",
            refresh_token="old-refresh-token",
            token_expiry=datetime.now(UTC) - timedelta(minutes=1),
        )
    )

    response = client.post("/api/integrations/pagerduty/test", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "pagerduty"
    assert data["ok"] is False
    assert "refresh failed" in data["details"].lower()


@pytest.mark.unit
def test_reconnect_updates_created_at():
    """On reconnect (upsert), created_at should reflect the new connection time."""
    import time

    headers, tenant_id = _run(_create_headers_and_tenant())

    _run(
        oauth_token_store.upsert_token(
            tenant_id=tenant_id,
            provider="pagerduty",
            access_token="token-v1",
        )
    )
    token_v1 = _run(oauth_token_store.get_token(tenant_id, "pagerduty"))
    first_created = token_v1.created_at

    time.sleep(0.05)

    _run(
        oauth_token_store.upsert_token(
            tenant_id=tenant_id,
            provider="pagerduty",
            access_token="token-v2",
        )
    )
    token_v2 = _run(oauth_token_store.get_token(tenant_id, "pagerduty"))

    assert token_v2.created_at > first_created
    assert token_v2.access_token == "token-v2"


@pytest.mark.unit
def test_onboarding_status_shows_reconnect_date():
    """Onboarding status endpoint should return the reconnect date, not the original."""
    import time

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    headers, tenant_id = _run(_create_headers_and_tenant())

    # First connection
    _run(
        oauth_token_store.upsert_token(
            tenant_id=tenant_id,
            provider="pagerduty",
            access_token="token-v1",
        )
    )
    token_v1 = _run(oauth_token_store.get_token(tenant_id, "pagerduty"))
    first_date = token_v1.created_at.isoformat()

    time.sleep(0.05)

    # Reconnect
    _run(
        oauth_token_store.upsert_token(
            tenant_id=tenant_id,
            provider="pagerduty",
            access_token="token-v2",
        )
    )
    token_v2 = _run(oauth_token_store.get_token(tenant_id, "pagerduty"))
    reconnect_date = token_v2.created_at.isoformat()

    assert reconnect_date > first_date

    # Onboarding status should show the reconnect date
    response = client.get("/dashboard/api/onboarding/status", headers=headers)
    assert response.status_code == 200
    data = response.json()
    details = data.get("details", {}).get("pagerduty", {})
    assert details.get("connected_at") == reconnect_date
