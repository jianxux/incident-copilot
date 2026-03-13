"""Integration tests for dashboard route prefixing behavior."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Ensure dashboard auth bypass is active for this module.
os.environ["SUPABASE_AUTH_ENABLED"] = "false"
os.environ["SUPABASE_DB_ENABLED"] = "false"
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_ANON_KEY", None)
os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)


@pytest.fixture(scope="module")
def client():
    from src import supabase_client
    from src.config import get_settings
    from src.main import create_app

    # Reset cached settings/feature checks to honor test env vars above.
    get_settings.cache_clear()
    supabase_client.is_supabase_configured.cache_clear()
    supabase_client.is_supabase_auth_enabled.cache_clear()
    supabase_client.is_supabase_db_enabled.cache_clear()

    # Keep tests hermetic: any accidental Supabase DB use should fail fast
    # and route-level fallback paths should handle it.
    monkeypatch = pytest.MonkeyPatch()

    def _disabled_get_db(*args, **kwargs):
        raise RuntimeError("Supabase disabled for tests")

    monkeypatch.setattr("src.db.supabase_db.get_db", _disabled_get_db)

    app = create_app()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        monkeypatch.undo()


def test_dashboard_onboarding_status_prefixed(client: TestClient):
    response = client.get("/dashboard/api/onboarding/status")
    assert response.status_code == 200

    payload = response.json()
    assert "authenticated" in payload
    assert "tenant" in payload
    assert "integrations" in payload
    assert "details" in payload


def test_dashboard_slack_manifest_prefixed(client: TestClient):
    response = client.get("/dashboard/integrations/slack/manifest")
    assert response.status_code == 200

    payload = response.json()
    assert "_metadata" in payload
    assert "display_information" in payload
    assert "oauth_config" in payload


def test_dashboard_pagerduty_sync_status_prefixed(client: TestClient):
    response = client.get("/dashboard/api/integrations/pagerduty/sync/status")
    assert response.status_code == 200

    payload = response.json()
    assert "connected" in payload
    assert "last_sync" in payload


@pytest.mark.parametrize(
    "path",
    [
        "/api/onboarding/status",
        "/integrations/slack/manifest",
        "/api/integrations/pagerduty/sync/status",
    ],
)
def test_unprefixed_dashboard_only_endpoints_404(client: TestClient, path: str):
    response = client.get(path)
    assert response.status_code == 404
