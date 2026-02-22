"""Tests for the service catalog store and API endpoints."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Ensure Supabase is disabled for unit tests
os.environ["SUPABASE_DB_ENABLED"] = "false"
os.environ.pop("SUPABASE_URL", None)

from src.services.models import (
    Service,
    ServiceCreate,
    ServiceCriticality,
    ServiceDependencyCreate,
    ServiceDependencyType,
    ServiceHealth,
    ServiceUpdate,
)
from src.services.store import ServiceCatalogStore


# ── Model Tests ────────────────────────────────────────────────────


class TestServiceModels:
    """Unit tests for Pydantic service models."""

    def test_service_create_minimal(self):
        s = ServiceCreate(name="my-service")
        assert s.name == "my-service"
        assert s.criticality == ServiceCriticality.MEDIUM
        assert s.tags == []

    def test_service_create_full(self):
        s = ServiceCreate(
            name="payments-api",
            description="Payment processing",
            team="platform",
            owner_email="eng@co.com",
            criticality=ServiceCriticality.CRITICAL,
            health=ServiceHealth.HEALTHY,
            tags=["payments", "core"],
            critical_user_journey=True,
            repo_url="https://github.com/org/payments",
            dashboard_url="https://grafana.co/payments",
            runbook_url="https://wiki.co/payments-runbook",
        )
        assert s.criticality == "critical"
        assert s.critical_user_journey is True
        assert len(s.tags) == 2

    def test_service_update_partial(self):
        u = ServiceUpdate(description="Updated desc")
        dumped = u.model_dump(exclude_unset=True)
        assert "description" in dumped
        assert "name" not in dumped

    def test_service_update_empty(self):
        u = ServiceUpdate()
        dumped = u.model_dump(exclude_unset=True)
        assert dumped == {}

    def test_service_criticality_enum(self):
        assert ServiceCriticality.CRITICAL == "critical"
        assert ServiceCriticality.HIGH == "high"

    def test_service_health_enum(self):
        assert ServiceHealth.HEALTHY == "healthy"
        assert ServiceHealth.DEGRADED == "degraded"

    def test_dependency_create(self):
        d = ServiceDependencyCreate(
            target_service_id="auth-service",
            dependency_type=ServiceDependencyType.SYNC,
            is_critical=True,
        )
        assert d.target_service_id == "auth-service"
        assert d.is_critical is True


# ── Store Tests (no DB) ───────────────────────────────────────────


class TestServiceCatalogStoreDisabled:
    """Tests for store behavior when Supabase is not configured."""

    @pytest.fixture(autouse=True)
    def _disable_supabase(self, monkeypatch):
        monkeypatch.setattr("src.services.store.is_supabase_db_enabled", lambda: False)

    def test_store_not_enabled_without_supabase(self):
        store = ServiceCatalogStore()
        assert store.enabled is False

    @pytest.mark.asyncio
    async def test_create_service_returns_fallback(self):
        store = ServiceCatalogStore()
        req = ServiceCreate(name="test-svc", description="A test service")
        result = await store.create_service(req, tenant_slug="default")
        assert result.name == "test-svc"
        assert result.id == "test-svc"
        assert result.description == "A test service"
        # Fallback — no tenant_id or timestamps
        assert result.created_at is None

    @pytest.mark.asyncio
    async def test_list_services_returns_empty(self):
        store = ServiceCatalogStore()
        result = await store.list_services()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_service_returns_none(self):
        store = ServiceCatalogStore()
        result = await store.get_service("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_service_returns_false(self):
        store = ServiceCatalogStore()
        result = await store.delete_service("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_update_service_returns_none(self):
        store = ServiceCatalogStore()
        req = ServiceUpdate(description="new desc")
        result = await store.update_service("nonexistent", req)
        assert result is None

    @pytest.mark.asyncio
    async def test_list_dependencies_returns_empty(self):
        store = ServiceCatalogStore()
        result = await store.list_dependencies()
        assert result == []


# ── Store Tests (mocked Supabase) ─────────────────────────────────


class TestServiceCatalogStoreWithMock:
    """Tests for store behavior with mocked Supabase client."""

    def _make_store(self):
        store = ServiceCatalogStore()
        store._enabled = True
        return store

    def _mock_client(self):
        client = MagicMock()
        return client

    def _mock_table(self, client, table_name, response_data):
        """Set up a mock table().select/insert/upsert/delete chain."""
        table = MagicMock()
        result = MagicMock()
        result.data = response_data

        # Chain methods return self for fluent API
        for method in ["select", "insert", "upsert", "update", "delete",
                       "eq", "or_", "limit", "order"]:
            getattr(table, method, None) or setattr(table, method, MagicMock(return_value=table))
            getattr(table, method).return_value = table

        table.execute.return_value = result
        client.table.return_value = table
        return table

    @pytest.mark.asyncio
    async def test_create_service_persists(self):
        store = self._make_store()
        client = self._mock_client()

        # Mock tenant lookup
        tenant_table = MagicMock()
        tenant_result = MagicMock()
        tenant_result.data = [{"id": "tenant-uuid-123"}]
        for m in ["select", "eq", "limit", "insert"]:
            getattr(tenant_table, m).return_value = tenant_table
        tenant_table.execute.return_value = tenant_result

        # Mock service upsert
        svc_table = MagicMock()
        svc_result = MagicMock()
        svc_result.data = [{
            "id": "svc-uuid",
            "service_key": "payments-api",
            "name": "payments-api",
            "tenant_id": "tenant-uuid-123",
            "description": "Pay stuff",
            "team": None,
            "owner_email": None,
            "criticality": "critical",
            "health": "unknown",
            "tags": [],
            "critical_user_journey": False,
            "repo_url": None,
            "dashboard_url": None,
            "runbook_url": None,
            "metadata": {},
            "created_at": "2026-02-18T00:00:00Z",
            "updated_at": "2026-02-18T00:00:00Z",
        }]
        for m in ["select", "eq", "limit", "upsert"]:
            getattr(svc_table, m).return_value = svc_table
        svc_table.execute.return_value = svc_result

        call_count = {"n": 0}
        def table_router(name):
            call_count["n"] += 1
            if name == "tenants":
                return tenant_table
            return svc_table

        client.table = table_router

        with patch.object(store, "_client", return_value=client):
            req = ServiceCreate(name="payments-api", description="Pay stuff", criticality=ServiceCriticality.CRITICAL)
            result = await store.create_service(req, tenant_slug="default")

        assert result.name == "payments-api"
        assert result.tenant_id == "tenant-uuid-123"
        assert result.criticality == "critical"
        assert result.created_at is not None

    @pytest.mark.asyncio
    async def test_list_services_returns_results(self):
        store = self._make_store()
        client = self._mock_client()

        tenant_table = MagicMock()
        tenant_result = MagicMock()
        tenant_result.data = [{"id": "t1"}]
        for m in ["select", "eq", "limit"]:
            getattr(tenant_table, m).return_value = tenant_table
        tenant_table.execute.return_value = tenant_result

        svc_table = MagicMock()
        svc_result = MagicMock()
        svc_result.data = [
            {"service_key": "svc-a", "name": "Service A", "tenant_id": "t1", "criticality": "high",
             "health": "healthy", "tags": ["core"], "critical_user_journey": True, "metadata": {}},
            {"service_key": "svc-b", "name": "Service B", "tenant_id": "t1", "criticality": "low",
             "health": "unknown", "tags": [], "critical_user_journey": False, "metadata": {}},
        ]
        for m in ["select", "eq", "order"]:
            getattr(svc_table, m).return_value = svc_table
        svc_table.execute.return_value = svc_result

        def table_router(name):
            return tenant_table if name == "tenants" else svc_table

        client.table = table_router

        with patch.object(store, "_client", return_value=client):
            results = await store.list_services(tenant_slug="default")

        assert len(results) == 2
        assert results[0].name == "Service A"
        assert results[0].criticality == "high"
        assert results[1].name == "Service B"

    @pytest.mark.asyncio
    async def test_delete_service_returns_true(self):
        store = self._make_store()
        client = self._mock_client()

        tenant_table = MagicMock()
        tenant_result = MagicMock()
        tenant_result.data = [{"id": "t1"}]
        for m in ["select", "eq", "limit"]:
            getattr(tenant_table, m).return_value = tenant_table
        tenant_table.execute.return_value = tenant_result

        del_table = MagicMock()
        del_result = MagicMock()
        del_result.data = [{"id": "deleted"}]
        for m in ["delete", "eq", "or_"]:
            getattr(del_table, m).return_value = del_table
        del_table.execute.return_value = del_result

        def table_router(name):
            return tenant_table if name == "tenants" else del_table

        client.table = table_router

        with patch.object(store, "_client", return_value=client):
            ok = await store.delete_service("svc-a", tenant_slug="default")

        assert ok is True

    @pytest.mark.asyncio
    async def test_db_error_graceful_fallback(self):
        """Store should not crash on DB errors — returns fallback."""
        store = self._make_store()

        def exploding_client():
            client = MagicMock()
            table = MagicMock()
            table.select.side_effect = Exception("connection refused")
            client.table.return_value = table
            return client

        with patch.object(store, "_client", side_effect=exploding_client):
            req = ServiceCreate(name="test")
            result = await store.create_service(req)
            # Should return fallback, not crash
            assert result.name == "test"
            assert result.created_at is None

    @pytest.mark.asyncio
    async def test_normalize_service_id(self):
        store = ServiceCatalogStore()
        assert store._normalize_service_id("My Cool Service") == "my-cool-service"
        assert store._normalize_service_id("api-gateway") == "api-gateway"
        assert store._normalize_service_id("Service (v2)") == "service-v2"


# ── Singleton Tests ────────────────────────────────────────────────


class TestServiceCatalogSingleton:
    def test_get_store_returns_same_instance(self):
        from src.services.store import get_service_catalog_store, service_catalog_store
        import src.services.store as store_mod

        # Reset
        store_mod.service_catalog_store = None
        s1 = store_mod.get_service_catalog_store()
        s2 = store_mod.get_service_catalog_store()
        assert s1 is s2
        store_mod.service_catalog_store = None  # cleanup
