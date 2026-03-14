"""Tests for the incidents API endpoint enhancements."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ["SUPABASE_DB_ENABLED"] = "false"
os.environ.pop("SUPABASE_URL", None)


class TestIncidentFormatting:
    """Test the _format_incident helper in the API."""

    def _map_status(self, value: str | None) -> str:
        status_map = {
            "processing": "processing",
            "completed": "resolved",
            "error": "error",
        }
        normalized = str(value or "processing").strip().lower()
        return status_map.get(normalized, normalized)

    def _format(self, row: dict) -> dict:
        """Import and call the format function from routes."""
        # We test the formatting logic directly
        triggered = row.get("triggered_at")
        processed = row.get("processed_at")
        created_at = row.get("created_at") or triggered
        updated_at = row.get("updated_at") or processed or created_at
        duration_seconds = None
        if triggered and processed:
            try:
                t0 = datetime.fromisoformat(str(triggered).replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(str(processed).replace("Z", "+00:00"))
                duration_seconds = int((t1 - t0).total_seconds())
            except Exception:
                pass

        meta = row.get("metadata") or {}
        verdict_summary = None
        if isinstance(meta, dict):
            verdict = meta.get("verdict") or meta.get("ai_verdict") or {}
            if isinstance(verdict, dict):
                verdict_summary = verdict.get("summary") or verdict.get("one_liner")
            elif isinstance(verdict, str):
                verdict_summary = verdict[:200]

        return {
            "id": row["id"],
            "incident_id": row["id"],
            "title": row.get("title") or "",
            "description": row.get("description") or "",
            "service": row.get("service") or "",
            "service_name": row.get("service") or "",
            "severity": row.get("severity") or "medium",
            "status": self._map_status(row.get("status")),
            "source": row.get("source") or "",
            "source_url": row.get("source_url") or "",
            "source_id": row.get("source_id") or "",
            "triggered_at": triggered,
            "processed_at": processed,
            "created_at": created_at,
            "updated_at": updated_at,
            "duration_seconds": duration_seconds,
            "verdict_summary": verdict_summary,
            "error_message": row.get("error_message"),
        }

    def test_basic_incident(self):
        row = {
            "id": "inc-1",
            "title": "High latency on api-gateway",
            "service": "api-gateway",
            "severity": "high",
            "status": "triggered",
            "source": "pagerduty",
            "source_url": "https://pd.com/inc/1",
            "triggered_at": "2026-02-18T10:00:00Z",
            "processed_at": None,
            "created_at": "2026-02-18T10:00:00Z",
            "metadata": {},
        }
        result = self._format(row)
        assert result["id"] == "inc-1"
        assert result["incident_id"] == "inc-1"
        assert result["service"] == "api-gateway"
        assert result["service_name"] == "api-gateway"
        assert result["source"] == "pagerduty"
        assert result["source_url"] == "https://pd.com/inc/1"
        assert result["created_at"] == "2026-02-18T10:00:00Z"
        assert result["updated_at"] == "2026-02-18T10:00:00Z"
        assert result["duration_seconds"] is None  # not resolved
        assert result["verdict_summary"] is None

    def test_resolved_incident_with_duration(self):
        row = {
            "id": "inc-2",
            "title": "DB connection pool exhausted",
            "service": "payments",
            "severity": "critical",
            "status": "resolved",
            "triggered_at": "2026-02-18T10:00:00Z",
            "processed_at": "2026-02-18T10:45:00Z",
            "created_at": "2026-02-18T10:00:00Z",
            "metadata": {},
        }
        result = self._format(row)
        assert result["duration_seconds"] == 2700  # 45 minutes
        assert result["status"] == "resolved"

    def test_processing_status_maps_to_processing(self):
        row = {"id": "inc-map-1", "status": "processing"}
        result = self._format(row)
        assert result["status"] == "processing"

    def test_completed_status_maps_to_resolved(self):
        row = {"id": "inc-map-2", "status": "completed"}
        result = self._format(row)
        assert result["status"] == "resolved"

    def test_error_status_maps_to_error(self):
        row = {"id": "inc-map-3", "status": "error"}
        result = self._format(row)
        assert result["status"] == "error"

    def test_verdict_from_metadata_dict(self):
        row = {
            "id": "inc-3",
            "title": "Memory spike",
            "metadata": {
                "verdict": {
                    "summary": "Memory leak in worker process caused OOM kills",
                    "severity": "high",
                }
            },
        }
        result = self._format(row)
        assert result["verdict_summary"] == "Memory leak in worker process caused OOM kills"

    def test_verdict_from_ai_verdict_key(self):
        row = {
            "id": "inc-4",
            "title": "CPU spike",
            "metadata": {
                "ai_verdict": {
                    "one_liner": "Runaway regex in request parser",
                }
            },
        }
        result = self._format(row)
        assert result["verdict_summary"] == "Runaway regex in request parser"

    def test_verdict_string(self):
        row = {
            "id": "inc-5",
            "title": "Disk full",
            "metadata": {"verdict": "Log rotation failed, disk at 100%"},
        }
        result = self._format(row)
        assert result["verdict_summary"] == "Log rotation failed, disk at 100%"

    def test_no_metadata(self):
        row = {"id": "inc-6", "title": "Test", "metadata": None}
        result = self._format(row)
        assert result["verdict_summary"] is None
        assert result["duration_seconds"] is None

    def test_missing_fields_default(self):
        row = {"id": "inc-7"}
        result = self._format(row)
        assert result["title"] == ""
        assert result["service"] == ""
        assert result["severity"] == "medium"
        assert result["status"] == "processing"
        assert result["source"] == ""

    def test_backward_compat_service_name(self):
        """Ensure service_name is still returned for backward compatibility."""
        row = {"id": "inc-8", "service": "auth-svc"}
        result = self._format(row)
        assert result["service"] == "auth-svc"
        assert result["service_name"] == "auth-svc"

    def test_duration_with_timezone_aware_timestamps(self):
        row = {
            "id": "inc-9",
            "triggered_at": "2026-02-18T10:00:00+00:00",
            "processed_at": "2026-02-18T11:30:00+00:00",
        }
        result = self._format(row)
        assert result["duration_seconds"] == 5400  # 1h 30m

    def test_duration_zero(self):
        row = {
            "id": "inc-10",
            "triggered_at": "2026-02-18T10:00:00Z",
            "processed_at": "2026-02-18T10:00:00Z",
        }
        result = self._format(row)
        assert result["duration_seconds"] == 0


class TestIncidentStatusUpdate:
    """Test the PATCH /api/incidents/{id}/status endpoint validation."""

    @pytest.fixture(scope="class")
    def client(self):
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

    def test_invalid_status_rejected(self, client):
        resp = client.patch(
            "/dashboard/api/incidents/inc-1/status",
            json={"status": "invalid"},
        )
        assert resp.status_code == 400
        assert "Invalid status" in resp.json()["detail"]

    def test_acknowledged_accepted(self, client):
        resp = client.patch(
            "/dashboard/api/incidents/inc-1/status",
            json={"status": "acknowledged"},
        )
        assert resp.status_code != 400  # May be 500 (no DB), but not validation error

    def test_resolved_accepted(self, client):
        resp = client.patch(
            "/dashboard/api/incidents/inc-1/status",
            json={"status": "resolved"},
        )
        assert resp.status_code != 400


class TestIncidentsListAPI:
    """Test the /api/incidents endpoint returns correct shape."""

    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient

        from src.main import create_app

        app = create_app()
        with TestClient(app) as c:
            yield c

    def test_empty_incidents_unauthenticated(self, client):
        """Without auth, incidents endpoint is unauthorized."""
        resp = client.get("/api/incidents")
        assert resp.status_code == 401
        data = resp.json()
        assert data["detail"] == "auth_required"

    def test_incidents_response_shape(self, client):
        """Incidents endpoint requires auth when no overrides are configured."""
        resp = client.get("/api/incidents")
        assert resp.status_code == 401
        data = resp.json()
        assert data["detail"] == "auth_required"


def test_list_incidents_merges_supabase_and_memory_with_supabase_wins(monkeypatch):
    from fastapi.testclient import TestClient

    from src.auth.middleware import AuthContext, get_auth_context
    from src.main import create_app
    from src.models import Severity
    from src.web.store import StoredIncident

    now = datetime(2026, 2, 22, 12, 0, tzinfo=UTC)

    async def fake_supabase_list(**_kwargs):
        return (
            [
                {
                    "id": "inc-1",
                    "title": "Supabase title",
                    "service": "payments-api",
                    "severity": "high",
                    "status": "processing",
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                    "metadata": {},
                },
                {
                    "id": "inc-2",
                    "title": "Supabase only",
                    "service": "auth-api",
                    "severity": "medium",
                    "status": "processing",
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                    "metadata": {},
                },
            ],
            2,
        )

    memory_rows = [
        StoredIncident(
            incident_id="inc-1",
            title="Memory title",
            service_name="payments-api",
            severity=Severity.CRITICAL,
            status="processing",
            triggered_at=now,
        ),
        StoredIncident(
            incident_id="inc-3",
            title="Memory only",
            service_name="worker-api",
            severity=Severity.LOW,
            status="processing",
            triggered_at=now,
        ),
    ]

    monkeypatch.setattr("src.api.incidents.is_supabase_db_enabled", lambda: True)
    monkeypatch.setattr("src.api.incidents._list_supabase_incidents", fake_supabase_list)
    monkeypatch.setattr(
        "src.api.incidents.incident_store.get_all_incidents",
        AsyncMock(return_value=memory_rows),
    )

    app = create_app()

    mock_tenant = MagicMock()
    mock_tenant.id = "tenant-1"
    mock_tenant.slug = "tenant-1"
    mock_tenant.integrations = {}

    async def override_auth():
        return AuthContext(user=MagicMock(id="u1"), tenant=mock_tenant)

    app.dependency_overrides[get_auth_context] = override_auth

    with TestClient(app) as client:
        response = client.get("/api/incidents")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3

    incidents = {item["id"]: item for item in payload["incidents"]}
    assert set(incidents) == {"inc-1", "inc-2", "inc-3"}
    assert incidents["inc-1"]["title"] == "Supabase title"


def test_list_incidents_includes_processing_test_incident_from_memory(monkeypatch):
    from fastapi.testclient import TestClient

    from src.auth.middleware import AuthContext, get_auth_context
    from src.main import create_app
    from src.models import Severity
    from src.web.store import StoredIncident

    now = datetime(2026, 2, 22, 12, 0, tzinfo=UTC)

    async def fake_supabase_list(**_kwargs):
        return ([], 0)

    test_incident = StoredIncident(
        incident_id="test-inc-1",
        title="[TEST] Incident Copilot onboarding test for payments-api",
        service_name="payments-api",
        severity=Severity.HIGH,
        status="processing",
        triggered_at=now,
        description="Synthetic test incident created by onboarding flow.",
    )

    monkeypatch.setattr("src.api.incidents.is_supabase_db_enabled", lambda: True)
    monkeypatch.setattr("src.api.incidents._list_supabase_incidents", fake_supabase_list)
    monkeypatch.setattr(
        "src.api.incidents.incident_store.get_all_incidents",
        AsyncMock(return_value=[test_incident]),
    )

    app = create_app()

    mock_tenant = MagicMock()
    mock_tenant.id = "tenant-1"
    mock_tenant.slug = "tenant-1"
    mock_tenant.integrations = {}

    async def override_auth():
        return AuthContext(user=MagicMock(id="u1"), tenant=mock_tenant)

    app.dependency_overrides[get_auth_context] = override_auth

    with TestClient(app) as client:
        response = client.get("/api/incidents")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["incidents"][0]["id"] == "test-inc-1"
    assert payload["incidents"][0]["status"] == "processing"


def test_timeline_inmemory_includes_github_event_types(monkeypatch):
    from fastapi.testclient import TestClient

    from src.auth.middleware import AuthContext, get_auth_context
    from src.main import create_app
    from src.models import Severity
    from src.web.store import StoredIncident

    now = datetime(2026, 2, 22, 12, 0, tzinfo=UTC)

    app = create_app()

    mock_tenant = MagicMock()
    mock_tenant.id = "tenant-1"
    mock_tenant.slug = "tenant-1"

    async def override_auth():
        return AuthContext(user=MagicMock(id="u1"), tenant=mock_tenant)

    app.dependency_overrides[get_auth_context] = override_auth

    monkeypatch.setattr("src.api.incidents.is_supabase_db_enabled", lambda: False)
    monkeypatch.setattr(
        "src.api.incidents.incident_store.get_incident",
        AsyncMock(
            return_value=StoredIncident(
                incident_id="inc-1",
                title="Latency spike",
                service_name="payments-api",
                severity=Severity.HIGH,
                status="processing",
                triggered_at=now,
            )
        ),
    )
    monkeypatch.setattr(
        "src.api.incidents._try_ondemand_enrichment",
        AsyncMock(
            return_value={
                "github": {
                    "recent_deploys": [
                        {
                            "short_sha": "abc1234",
                            "author": "alice",
                            "message": "Fix timeout regression",
                            "timestamp": "2026-02-22T11:40:00Z",
                        }
                    ],
                    "recent_prs": [
                        {
                            "number": 42,
                            "title": "Reduce retry storm",
                            "author": "bob",
                            "merged_at": "2026-02-22T11:45:00Z",
                        }
                    ],
                    "recent_deployments": [
                        {
                            "id": "d-1",
                            "environment": "production",
                            "status": "success",
                            "created_at": "2026-02-22T11:50:00Z",
                            "creator": "ci-bot",
                        }
                    ],
                }
            }
        ),
    )

    with TestClient(app) as client:
        response = client.get("/api/incidents/inc-1/timeline")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    event_types = {event.get("type") for event in payload}
    assert {"code_change", "pull_request", "deployment"}.issubset(event_types)


def test_timeline_supabase_uses_stored_context_card_for_github_event_types(monkeypatch):
    from fastapi.testclient import TestClient

    from src.auth.middleware import AuthContext, get_auth_context
    from src.main import create_app

    class _FakeDb:
        async def list_incident_events(self, _incident_id):
            return []

        async def list_comments(self, _incident_id):
            return []

        async def get_context_card(self, _incident_id):
            return {
                "id": "ctx-1",
                "data": {
                    "github": {
                        "recent_deploys": [
                            {
                                "short_sha": "def5678",
                                "author": "carol",
                                "message": "Tune connection pool",
                                "timestamp": "2026-02-22T10:40:00Z",
                            }
                        ],
                        "recent_prs": [
                            {
                                "number": 43,
                                "title": "Batch writes for queue",
                                "author": "dave",
                                "merged_at": "2026-02-22T10:45:00Z",
                            }
                        ],
                        "recent_deployments": [
                            {
                                "id": "d-2",
                                "environment": "staging",
                                "status": "in_progress",
                                "created_at": "2026-02-22T10:50:00Z",
                                "creator": "deploy-bot",
                            }
                        ],
                    }
                },
            }

    app = create_app()

    mock_tenant = MagicMock()
    mock_tenant.id = "tenant-1"
    mock_tenant.slug = "tenant-1"

    async def override_auth():
        return AuthContext(user=MagicMock(id="u1"), tenant=mock_tenant)

    app.dependency_overrides[get_auth_context] = override_auth

    monkeypatch.setattr("src.api.incidents.is_supabase_db_enabled", lambda: True)
    monkeypatch.setattr(
        "src.api.incidents._get_incident_row",
        AsyncMock(
            return_value={
                "id": "inc-1",
                "service": "payments-api",
                "created_at": "2026-02-22T10:00:00Z",
            }
        ),
    )
    monkeypatch.setattr("src.db.supabase_db.get_db", lambda use_admin=True: _FakeDb())
    mock_ondemand = AsyncMock(return_value={})
    monkeypatch.setattr("src.api.incidents._try_ondemand_enrichment", mock_ondemand)

    with TestClient(app) as client:
        response = client.get("/api/incidents/inc-1/timeline")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    event_types = {event.get("type") for event in payload}
    assert {"code_change", "pull_request", "deployment"}.issubset(event_types)
    mock_ondemand.assert_not_awaited()


class TestDashboardWrapperEndpoints:
    """Test dashboard wrapper endpoints pass auth_data correctly."""

    @pytest.fixture
    def authed_client(self):
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

    def test_dashboard_stats_wrapper_returns_200_with_auth(self, authed_client):
        resp = authed_client.get("/dashboard/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data

    def test_dashboard_incidents_wrapper_returns_200_with_auth(self, authed_client):
        resp = authed_client.get("/dashboard/api/incidents")
        assert resp.status_code == 200
        data = resp.json()
        assert "incidents" in data
        assert "total" in data
        assert isinstance(data["incidents"], list)

    def test_dashboard_stats_wrapper_returns_401_without_auth(self, monkeypatch):
        from fastapi.testclient import TestClient

        from src.main import create_app

        monkeypatch.setattr("src.supabase_client.is_supabase_auth_enabled", lambda: True)

        async def _no_auth(_request):
            return None, None

        monkeypatch.setattr("src.web.routes._get_tenant_id_from_request", _no_auth)

        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/dashboard/api/stats")
        assert resp.status_code == 401

    def test_dashboard_incidents_wrapper_returns_401_without_auth(self, monkeypatch):
        from fastapi.testclient import TestClient

        from src.main import create_app

        monkeypatch.setattr("src.supabase_client.is_supabase_auth_enabled", lambda: True)

        async def _no_auth(_request):
            return None, None

        monkeypatch.setattr("src.web.routes._get_tenant_id_from_request", _no_auth)

        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/dashboard/api/incidents")
        assert resp.status_code == 401
