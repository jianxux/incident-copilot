"""API tests for analytics dashboard endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_analytics_summary_endpoint(client):
    response = client.get("/api/analytics/summary", params={"period": "week"})

    assert response.status_code == 200
    data = response.json()

    assert data["period"] == "week"

    incidents = data["incidents"]
    assert set(incidents.keys()) == {
        "total_incidents",
        "resolved_incidents",
        "open_incidents",
        "mttr_hours",
        "mtta_minutes",
        "by_severity",
        "by_source",
        "change_from_previous",
    }
    assert set(incidents["by_severity"].keys()) == {
        "critical",
        "high",
        "medium",
        "low",
        "info",
    }
    assert set(incidents["change_from_previous"].keys()) == {
        "incidents",
        "mttr",
        "mtta",
    }

    assert isinstance(data["team_performance"], list)
    assert isinstance(data["service_health"], list)
    assert isinstance(data["trends"], list)


def test_mttr_endpoint_accepts_period(client):
    response = client.get("/api/analytics/mttr", params={"period": "day"})

    assert response.status_code == 200
    data = response.json()

    assert data["period"] == "day"
    assert "period_start" in data
    assert "period_end" in data
    assert "incidents_count" in data
    assert "resolved_count" in data


def test_teams_endpoint(client):
    response = client.get("/api/analytics/teams")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) > 0

    first = data[0]
    assert set(first.keys()) == {
        "team_id",
        "team_name",
        "incidents_handled",
        "avg_response_time_minutes",
        "avg_resolution_time_hours",
        "on_call_hours",
        "escalation_rate",
    }


def test_services_endpoint(client):
    response = client.get("/api/analytics/services")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) > 0

    first = data[0]
    assert set(first.keys()) == {
        "service_id",
        "service_name",
        "incident_count",
        "critical_count",
        "uptime_percentage",
        "last_incident",
        "trend",
    }


def test_heatmap_endpoint(client):
    response = client.get("/api/analytics/heatmap")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) == 168

    first = data[0]
    assert set(first.keys()) == {"day_of_week", "hour_of_day", "incident_count"}

    day_hour_pairs = {(row["day_of_week"], row["hour_of_day"]) for row in data}
    assert len(day_hour_pairs) == 168
    assert (0, 0) in day_hour_pairs
    assert (6, 23) in day_hour_pairs
