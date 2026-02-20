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
    return {"Authorization": f"Bearer {session.access_token}"}


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

    connect = client.get("/api/integrations/slack/connect", headers=headers, follow_redirects=False)
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

    connect = client.get("/api/integrations/slack/connect", headers=headers, follow_redirects=False)
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
