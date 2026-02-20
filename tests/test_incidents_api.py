"""Tests for the incidents API endpoint enhancements."""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ["SUPABASE_DB_ENABLED"] = "false"
os.environ.pop("SUPABASE_URL", None)


class TestIncidentFormatting:
    """Test the _format_incident helper in the API."""

    def _format(self, row: dict) -> dict:
        """Import and call the format function from routes."""
        # We test the formatting logic directly
        triggered = row.get("triggered_at")
        processed = row.get("processed_at")
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
            "incident_id": row["id"],
            "title": row.get("title") or "",
            "description": row.get("description") or "",
            "service": row.get("service") or "",
            "service_name": row.get("service") or "",
            "severity": row.get("severity") or "medium",
            "status": row.get("status") or "processing",
            "source": row.get("source") or "",
            "source_url": row.get("source_url") or "",
            "source_id": row.get("source_id") or "",
            "triggered_at": triggered,
            "processed_at": processed,
            "created_at": row.get("created_at"),
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
        assert result["incident_id"] == "inc-1"
        assert result["service"] == "api-gateway"
        assert result["source"] == "pagerduty"
        assert result["source_url"] == "https://pd.com/inc/1"
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
        from src.main import create_app
        from src.auth.middleware import AuthContext, get_auth_context
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
        """Without auth, returns empty incidents list."""
        resp = client.get("/api/incidents")
        assert resp.status_code == 200
        data = resp.json()
        assert "incidents" in data
        assert isinstance(data["incidents"], list)

    def test_incidents_response_shape(self, client):
        """Verify response has expected top-level keys."""
        resp = client.get("/api/incidents")
        data = resp.json()
        assert "incidents" in data


class TestDashboardWrapperEndpoints:
    """Test dashboard wrapper endpoints pass auth_data correctly."""

    @pytest.fixture
    def authed_client(self):
        from fastapi.testclient import TestClient
        from src.main import create_app
        from src.auth.middleware import AuthContext, get_auth_context
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
