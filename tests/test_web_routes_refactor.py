"""Regression tests for web routes module refactor."""

from importlib import import_module

from fastapi.testclient import TestClient

from src.main import app
from src.web import routes as routes_pkg
from src.web.routes import common
from src.web.store import incident_store


def test_route_modules_exist_and_are_importable():
    module_names = [
        "api",
        "common",
        "config",
        "demo",
        "onboarding",
        "pagerduty",
        "pages",
    ]
    for name in module_names:
        module = import_module(f"src.web.routes.{name}")
        assert module is not None


def test_shared_routers_have_reasonable_route_registration():
    route_paths = {route.path for route in common.router.routes}
    landing_paths = {route.path for route in common.landing_router.routes}

    assert len(common.router.routes) > 20
    assert len(common.router.routes) + len(common.landing_router.routes) > 20

    # Paths sampled from each split module to ensure side-effect registration happened.
    assert "/dashboard/config" in route_paths  # config.py
    assert "/dashboard/demo" in route_paths  # demo.py
    assert "/dashboard/api/onboarding/status" in route_paths  # onboarding.py
    assert "/dashboard/api/integrations/pagerduty/sync" in route_paths  # pagerduty.py
    assert "/dashboard/insights" in route_paths  # pages.py
    assert "/api/health" in landing_paths  # api.py


def test_init_exports_are_preserved():
    expected_exports = {
        "router",
        "landing_router",
        "incident_store",
        "DashboardAuthRedirect",
        "require_dashboard_auth",
        "_get_tenant_id_from_request",
        "_map_status",
        "status_color",
        "incident_detail",
        "incident_chat",
        "incident_timeline",
    }

    assert expected_exports.issubset(set(routes_pkg.__all__))
    assert routes_pkg.router is common.router
    assert routes_pkg.landing_router is common.landing_router
    assert routes_pkg.incident_store is incident_store
    assert routes_pkg.require_dashboard_auth is common.require_dashboard_auth


def test_landing_page_returns_200_with_branding():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Incident Copilot" in response.text


def test_dashboard_without_auth_redirects_to_login(monkeypatch):
    monkeypatch.setattr("src.supabase_client.is_supabase_auth_enabled", lambda: True)
    with TestClient(app) as client:
        response = client.get(
            "/dashboard/",
            headers={"accept": "text/html"},
            follow_redirects=False,
        )
    assert response.status_code in {302, 303, 307}
    assert response.headers["location"].startswith("/login")


def test_demo_route_returns_200_with_auth_override():
    async def _auth_override():
        return {"tenant_id": "default", "user_id": "test-user"}

    app.dependency_overrides[common.require_dashboard_auth] = _auth_override
    try:
        with TestClient(app) as client:
            response = client.get("/dashboard/demo")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(common.require_dashboard_auth, None)


def test_api_health_route_returns_200():
    with TestClient(app) as client:
        response = client.get("/dashboard/api/health")
        if response.status_code == 404:
            # Backward-compatible location in the refactored module.
            response = client.get("/api/health")
    assert response.status_code == 200


def test_onboarding_routes_are_registered():
    route_paths = {route.path for route in common.router.routes}
    assert "/dashboard/api/onboarding/status" in route_paths
    assert "/dashboard/api/onboarding/checklist" in route_paths
    assert "/dashboard/api/onboarding/test-incident" in route_paths


def test_pagerduty_routes_are_registered():
    route_paths = {route.path for route in common.router.routes}
    assert "/dashboard/api/integrations/pagerduty/sync" in route_paths
    assert "/dashboard/api/integrations/pagerduty/sync/status" in route_paths


def test_config_routes_are_registered():
    route_paths = {route.path for route in common.router.routes}
    assert "/dashboard/config" in route_paths
