"""Tests for incident detail/context/stats API endpoints and enhanced GitHub adapter."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ["SUPABASE_DB_ENABLED"] = "false"
os.environ.pop("SUPABASE_URL", None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def authed_client():
    """FastAPI TestClient with auth overrides and a clean incident store."""
    from fastapi.testclient import TestClient

    from src.auth.middleware import AuthContext, get_auth_context
    from src.main import create_app
    from src.web.routes import require_dashboard_auth

    app = create_app()

    mock_tenant = MagicMock()
    mock_tenant.id = "test-tenant"
    mock_tenant.slug = "test"
    mock_tenant.integrations = {}

    async def override_auth():
        return AuthContext(user=MagicMock(id="u1"), tenant=mock_tenant)

    async def override_dashboard_auth():
        return {"tenant_id": "test-tenant", "user_id": "u1"}

    app.dependency_overrides[get_auth_context] = override_auth
    app.dependency_overrides[require_dashboard_auth] = override_dashboard_auth

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def _seed_incident():
    """Seed the in-memory incident store with one completed incident."""
    import asyncio

    from src.models import ContextCard, GitHubContext, Severity
    from src.web.store import incident_store

    inc_id = "test-inc-001"
    now = datetime.now(UTC)

    async def _seed():
        await incident_store.add_incident(
            incident_id=inc_id,
            title="Latency spike in checkout",
            service_name="checkout-api",
            severity=Severity.HIGH,
            triggered_at=now - timedelta(minutes=30),
            source="pagerduty",
            source_url="https://pd.com/inc/001",
        )
        card = ContextCard(
            incident_id=inc_id,
            title="Latency spike in checkout",
            severity=Severity.HIGH,
            service_name="checkout-api",
            triggered_at=now - timedelta(minutes=30),
            alert_url="https://pd.com/inc/001",
            github=GitHubContext(
                repo="myco/checkout-api",
                recent_deploys=[],
                codeowners=["@platform"],
            ),
        )
        await incident_store.complete_incident(inc_id, card)

    asyncio.run(_seed())
    yield inc_id

    # cleanup
    async def _cleanup():
        store = incident_store
        if hasattr(store, "_incidents"):
            store._incidents.pop(inc_id, None)
            if inc_id in store._order:
                store._order.remove(inc_id)

    asyncio.run(_cleanup())


# ---------------------------------------------------------------------------
# GET /api/incidents/{id}
# ---------------------------------------------------------------------------


class TestIncidentDetailEndpoint:
    def test_returns_incident(self, authed_client, _seed_incident):
        inc_id = _seed_incident
        resp = authed_client.get(f"/api/incidents/{inc_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == inc_id
        assert data["title"] == "Latency spike in checkout"
        assert data["service"] == "checkout-api"
        assert data["severity"] == "high"
        assert data["status"] == "resolved"
        assert data["source"] == "manual"
        assert "created_at" in data
        assert "updated_at" in data

    def test_returns_404_for_missing(self, authed_client):
        resp = authed_client.get("/api/incidents/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/incidents/{id}/context
# ---------------------------------------------------------------------------


class TestIncidentContextEndpoint:
    def test_returns_context_card(self, authed_client, _seed_incident):
        inc_id = _seed_incident
        resp = authed_client.get(f"/api/incidents/{inc_id}/context")
        assert resp.status_code == 200
        data = resp.json()
        assert data["incident_id"] == inc_id
        assert data["service_name"] == "checkout-api"
        assert data["github"]["repo"] == "myco/checkout-api"

    def test_returns_404_for_missing(self, authed_client):
        resp = authed_client.get("/api/incidents/nonexistent-id/context")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/incidents/stats
# ---------------------------------------------------------------------------


class TestIncidentStatsEndpoint:
    def test_returns_stats_shape(self, authed_client):
        resp = authed_client.get("/api/incidents/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "by_status" in data
        assert "by_severity" in data
        assert "mttr_hours" in data
        assert "mtta_minutes" in data
        assert "incidents_today" in data
        assert "incidents_week" in data

    def test_stats_with_seeded_data(self, authed_client, _seed_incident):
        resp = authed_client.get("/api/incidents/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_stats_not_captured_by_incident_id_route(self, authed_client):
        """Ensure /stats is not treated as an incident_id."""
        resp = authed_client.get("/api/incidents/stats")
        assert resp.status_code == 200
        # Should NOT be a 404 (which would happen if 'stats' matched /{incident_id})
        assert "total" in resp.json()


# ---------------------------------------------------------------------------
# GitHub adapter: new model types
# ---------------------------------------------------------------------------


class TestGitHubModels:
    def test_github_pull_request_model(self):
        from src.models import GitHubPullRequest

        pr = GitHubPullRequest(
            number=42,
            title="Fix connection pool",
            author="alice",
            merged_at=datetime.now(UTC),
            url="https://github.com/myco/svc/pull/42",
            additions=10,
            deletions=3,
        )
        assert pr.number == 42
        assert pr.additions == 10

    def test_github_deployment_model(self):
        from src.models import GitHubDeployment

        dep = GitHubDeployment(
            id="dep-1",
            environment="production",
            status="success",
            created_at=datetime.now(UTC),
            url=None,
            creator="deploy-bot",
        )
        assert dep.environment == "production"
        assert dep.creator == "deploy-bot"

    def test_github_context_includes_new_fields(self):
        from src.models import GitHubContext, GitHubDeployment, GitHubPullRequest

        ctx = GitHubContext(
            repo="myco/svc",
            recent_prs=[
                GitHubPullRequest(
                    number=1,
                    title="PR 1",
                    author="bob",
                    merged_at=datetime.now(UTC),
                )
            ],
            recent_deployments=[
                GitHubDeployment(
                    id="d1",
                    environment="staging",
                    status="success",
                    created_at=datetime.now(UTC),
                    creator="ci",
                )
            ],
        )
        assert len(ctx.recent_prs) == 1
        assert len(ctx.recent_deployments) == 1
        assert ctx.recent_prs[0].author == "bob"


# ---------------------------------------------------------------------------
# GitHub adapter: get_context with mocked HTTP
# ---------------------------------------------------------------------------


class TestGitHubAdapterEnhanced:
    @pytest.fixture()
    def adapter(self):
        from src.integrations.github import GitHubAdapter

        settings = MagicMock()
        settings.github_token = "ghp_test"
        settings.github_org = "myco"
        settings.service_repo_map = {}
        return GitHubAdapter(settings)

    @pytest.mark.asyncio
    async def test_get_context_fetches_prs_and_deployments(self, adapter):
        """get_context should populate recent_prs and recent_deployments."""
        now = datetime.now(UTC)
        now_z = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        commits_json = [
            {
                "sha": "abc1234567890",
                "commit": {
                    "author": {"name": "alice", "date": now_z},
                    "message": "fix: timeout",
                },
                "html_url": "https://github.com/myco/svc/commit/abc",
            }
        ]
        prs_json = [
            {
                "number": 10,
                "title": "Merged PR",
                "user": {"login": "alice"},
                "merged_at": now_z,
                "html_url": "https://github.com/myco/svc/pull/10",
                "additions": 5,
                "deletions": 2,
            },
            {
                "number": 11,
                "title": "Unmerged PR",
                "user": {"login": "bob"},
                "merged_at": None,
                "html_url": "https://github.com/myco/svc/pull/11",
            },
        ]
        deployments_json = [
            {
                "id": 999,
                "environment": "production",
                "created_at": now_z,
                "creator": {"login": "deploy-bot"},
                "url": "https://api.github.com/repos/myco/svc/deployments/999",
                "statuses_url": "https://api.github.com/repos/myco/svc/deployments/999/statuses",
            }
        ]
        statuses_json = [{"state": "success"}]

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            if "/commits" in url:
                resp.status_code = 200
                resp.json.return_value = commits_json
            elif "/pulls" in url:
                resp.status_code = 200
                resp.json.return_value = prs_json
            elif "/statuses" in url:
                resp.status_code = 200
                resp.json.return_value = statuses_json
            elif "/deployments" in url:
                resp.status_code = 200
                resp.json.return_value = deployments_json
            elif "/contents/" in url:
                resp.status_code = 404
                resp.json.return_value = {}
            else:
                resp.status_code = 404
                resp.json.return_value = {}
            return resp

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            ctx = await adapter.get_context("svc", since_hours=24)

        assert ctx is not None
        assert ctx.repo == "myco/svc"
        assert len(ctx.recent_deploys) == 1
        assert len(ctx.recent_prs) == 1  # only the merged one
        assert ctx.recent_prs[0].number == 10
        assert len(ctx.recent_deployments) == 1
        assert ctx.recent_deployments[0].status == "success"

    @pytest.mark.asyncio
    async def test_get_context_handles_api_errors_gracefully(self, adapter):
        """get_context should return partial data when some API calls fail."""
        now = datetime.now(UTC)
        now_z = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        commits_json = [
            {
                "sha": "abc1234567890",
                "commit": {
                    "author": {"name": "alice", "date": now_z},
                    "message": "fix: timeout",
                },
                "html_url": "https://github.com/myco/svc/commit/abc",
            }
        ]

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            if "/commits" in url:
                resp.status_code = 200
                resp.json.return_value = commits_json
            elif "/pulls" in url:
                resp.status_code = 403
                resp.json.return_value = {"message": "forbidden"}
            elif "/deployments" in url:
                resp.status_code = 404
                resp.json.return_value = {}
            elif "/contents/" in url:
                resp.status_code = 404
                resp.json.return_value = {}
            else:
                resp.status_code = 404
                resp.json.return_value = {}
            return resp

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            ctx = await adapter.get_context("svc", since_hours=24)

        assert ctx is not None
        assert len(ctx.recent_deploys) == 1
        assert ctx.recent_prs == []
        assert ctx.recent_deployments == []
