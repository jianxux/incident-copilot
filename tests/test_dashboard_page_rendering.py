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
