"""Regression tests for dashboard page template rendering."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.main import create_app


def test_dashboard_config_page_renders_without_template_errors():
    """Ensure /dashboard/config renders successfully."""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/dashboard/config")

    assert response.status_code == 200
    assert "Configuration" in response.text


def test_dashboard_incidents_page_renders_without_template_errors():
    """Ensure /dashboard/incidents renders successfully."""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/dashboard/incidents")

    assert response.status_code == 200
    assert "Incidents" in response.text


def test_dashboard_analytics_page_renders_without_template_errors():
    """Ensure /dashboard/analytics renders successfully."""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/dashboard/analytics")

    assert response.status_code == 200
    assert "Analytics" in response.text


def test_dashboard_insights_page_renders_without_template_errors():
    """Ensure /dashboard/insights renders successfully."""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/dashboard/insights")

    assert response.status_code == 200
    assert "Insights" in response.text


def test_connect_integrations_button_hidden_by_default():
    """The 'Connect integrations' button should start hidden (no sm:inline-flex class)
    and only be shown by JS after checking onboarding status."""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/dashboard")
    assert response.status_code == 200
    # Button exists but is hidden (no sm:inline-flex in the static HTML)
    assert 'id="connect-integrations-btn"' in response.text
    assert 'class="hidden items-center' in response.text


def test_connect_integrations_button_js_logic_present():
    """Verify the JS that checks /api/onboarding/status is in the page."""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/dashboard")
    assert response.status_code == 200
    assert "/dashboard/api/onboarding/status" in response.text
    assert "connect-integrations-btn" in response.text
    assert "hasAlerting" in response.text
