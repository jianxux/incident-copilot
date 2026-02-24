"""Integration test fixtures for local Supabase."""

from __future__ import annotations

import os
import uuid

import pytest

from supabase import create_client

# Local Supabase defaults (from `supabase start`)
LOCAL_SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "http://127.0.0.1:54321"
)
LOCAL_SUPABASE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY", "sb_secret_N7UND0UgjKTVK-Uodkm0Hg_xSvEMPvz"
)


@pytest.fixture(scope="session")
def supabase_client():
    """Create a Supabase client pointing at local instance."""
    client = create_client(LOCAL_SUPABASE_URL, LOCAL_SUPABASE_KEY)
    # Verify connectivity
    result = client.table("tenants").select("id").limit(1).execute()
    assert result is not None, "Cannot connect to local Supabase"
    return client


@pytest.fixture()
def test_tenant(supabase_client):
    """Create an isolated test tenant, clean up after."""
    tenant_id = str(uuid.uuid4())
    slug = f"test-{tenant_id[:8]}"
    supabase_client.table("tenants").insert({
        "id": tenant_id,
        "name": f"Test Tenant {slug}",
        "slug": slug,
        "plan": "free",
    }).execute()

    yield tenant_id

    # Cleanup: delete tenant cascades to incidents, events, etc.
    supabase_client.table("tenants").delete().eq("id", tenant_id).execute()


@pytest.fixture()
def test_incidents(supabase_client, test_tenant):
    """Insert sample incidents for testing."""
    incidents = []
    for i in range(5):
        incident = {
            "id": str(uuid.uuid4()),
            "tenant_id": test_tenant,
            "source": "manual",
            "source_id": f"test-{uuid.uuid4().hex[:12]}",
            "title": f"Test incident {i+1}: API latency spike",
            "service": f"service-{chr(97+i)}",
            "severity": ["critical", "high", "medium", "low", "info"][i],
            "status": "resolved" if i < 3 else "triggered",
            "triggered_at": f"2026-02-{20+i}T10:00:00Z",
            "metadata": {"test": True, "index": i},
        }
        supabase_client.table("incidents").insert(incident).execute()
        incidents.append(incident)

    yield incidents
