import asyncio

import pytest
from fastapi.testclient import TestClient


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def create_authed_headers(auth_service):
    tenant = await auth_service.create_tenant(
        name="Test Tenant",
        slug=f"test-{asyncio.get_running_loop().time()}".replace(".", "-"),
    )
    user = await auth_service.create_user(
        email=f"user-{tenant.id}@example.com",
        name="Test User",
        tenant_id=tenant.id,
    )
    session = await auth_service.create_session(user.id)
    return tenant, {"Authorization": f"Bearer {session.access_token}"}


@pytest.mark.unit
def test_onboarding_checklist_defaults_without_auth():
    """Without auth, the checklist should return 200 using the default tenant."""
    from src.main import create_app

    app = create_app()
    client = TestClient(app)

    res = client.get("/dashboard/api/onboarding/checklist")
    assert res.status_code == 200
    data = res.json()
    assert data["tenant_id"] == "default"


@pytest.mark.unit
def test_onboarding_checklist_happy_path():
    from src.auth.service import auth_service
    from src.main import create_app

    app = create_app()
    client = TestClient(app)

    tenant, headers = run(create_authed_headers(auth_service))

    res = client.get("/dashboard/api/onboarding/checklist", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["tenant_id"] == tenant.id

    res2 = client.post(
        "/dashboard/api/onboarding/checklist/connect_slack?done=true", headers=headers
    )
    assert res2.status_code == 200
    data2 = res2.json()
    step = next(s for s in data2["steps"] if s["id"] == "connect_slack")
    assert step["done"] is True


@pytest.mark.unit
def test_onboarding_test_incident_starts():
    from src.auth.service import auth_service
    from src.main import create_app

    app = create_app()
    client = TestClient(app)

    _, headers = run(create_authed_headers(auth_service))

    res = client.post("/dashboard/api/onboarding/test-incident", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "incident_id" in data
