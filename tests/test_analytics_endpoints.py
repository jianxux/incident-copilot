"""Tests for analytics API endpoints (summary, teams, services, heatmap)."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestAnalyticsSummary:
    """Tests for GET /api/analytics/summary."""

    def test_summary_default_period(self, client):
        resp = client.get("/api/analytics/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "week"
        assert "incidents" in data
        assert "team_performance" in data
        assert "service_health" in data
        assert "trends" in data

    def test_summary_incident_fields(self, client):
        resp = client.get("/api/analytics/summary?period=month")
        data = resp.json()
        inc = data["incidents"]
        assert "total_incidents" in inc
        assert "resolved_incidents" in inc
        assert "open_incidents" in inc
        assert "mttr_hours" in inc
        assert "mtta_minutes" in inc
        assert "by_severity" in inc
        assert "by_source" in inc
        assert "change_from_previous" in inc

    def test_summary_severity_breakdown(self, client):
        resp = client.get("/api/analytics/summary")
        sev = resp.json()["incidents"]["by_severity"]
        for key in ("critical", "high", "medium", "low", "info"):
            assert key in sev
            assert isinstance(sev[key], int)

    def test_summary_change_from_previous(self, client):
        resp = client.get("/api/analytics/summary")
        change = resp.json()["incidents"]["change_from_previous"]
        for key in ("incidents", "mttr", "mtta"):
            assert key in change

    @pytest.mark.parametrize("period", ["day", "week", "month", "quarter"])
    def test_summary_all_periods(self, client, period):
        resp = client.get(f"/api/analytics/summary?period={period}")
        assert resp.status_code == 200
        assert resp.json()["period"] == period

    def test_summary_trends_have_dates(self, client):
        resp = client.get("/api/analytics/summary?period=week")
        trends = resp.json()["trends"]
        assert len(trends) > 0
        for t in trends:
            assert "date" in t
            assert "incidents" in t
            assert "resolved" in t


class TestTeamsEndpoint:
    """Tests for GET /api/analytics/teams."""

    def test_teams_returns_list(self, client):
        resp = client.get("/api/analytics/teams")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_teams_fields(self, client):
        resp = client.get("/api/analytics/teams")
        team = resp.json()[0]
        for field in (
            "team_id",
            "team_name",
            "incidents_handled",
            "avg_response_time_minutes",
            "avg_resolution_time_hours",
            "on_call_hours",
            "escalation_rate",
        ):
            assert field in team


class TestServicesEndpoint:
    """Tests for GET /api/analytics/services."""

    def test_services_returns_list(self, client):
        resp = client.get("/api/analytics/services")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_services_fields(self, client):
        resp = client.get("/api/analytics/services")
        svc = resp.json()[0]
        for field in (
            "service_id",
            "service_name",
            "incident_count",
            "critical_count",
            "uptime_percentage",
            "trend",
        ):
            assert field in svc

    def test_services_trend_values(self, client):
        resp = client.get("/api/analytics/services")
        for svc in resp.json():
            assert svc["trend"] in ("improving", "stable", "degrading")


class TestHeatmapEndpoint:
    """Tests for GET /api/analytics/heatmap."""

    def test_heatmap_returns_168_entries(self, client):
        resp = client.get("/api/analytics/heatmap")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 7 * 24  # 168

    def test_heatmap_fields(self, client):
        resp = client.get("/api/analytics/heatmap")
        entry = resp.json()[0]
        assert "day_of_week" in entry
        assert "hour_of_day" in entry
        assert "incident_count" in entry

    def test_heatmap_ranges(self, client):
        resp = client.get("/api/analytics/heatmap")
        for entry in resp.json():
            assert 0 <= entry["day_of_week"] <= 6
            assert 0 <= entry["hour_of_day"] <= 23
            assert entry["incident_count"] >= 0
