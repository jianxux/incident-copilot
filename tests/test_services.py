"""Tests for services module (service catalog)."""

import pytest

from src.services.models import (
    Service,
    ServiceCreate,
    ServiceCriticality,
    ServiceDependency,
    ServiceEnvironment,
)
from src.services.store import ServiceCatalogStore


class TestServiceModels:
    def test_service_creation(self):
        s = Service(
            id="svc-1",
            name="payments-api",
            description="Payment processing service",
            team="payments",
            tenant_id="t-1",
        )
        assert s.name == "payments-api"

    def test_service_criticality(self):
        assert ServiceCriticality.HIGH
        assert ServiceCriticality.LOW

    def test_service_dependency(self):
        d = ServiceDependency(
            source_service_id="svc-1",
            target_service_id="svc-2",
        )
        assert d.source_service_id == "svc-1"

    def test_service_environment(self):
        e = ServiceEnvironment(
            service_id="svc-1",
            environment="production",
            region="us-east-1",
        )
        assert e.environment == "production"

    def test_service_create(self):
        sc = ServiceCreate(
            name="new-svc",
            description="A new service",
        )
        assert sc.name == "new-svc"


class TestServiceCatalogStore:
    @pytest.fixture
    def store(self):
        return ServiceCatalogStore()

    def test_store_instantiation(self, store):
        assert store is not None

    @pytest.mark.asyncio
    async def test_list_services(self, store):
        services = await store.list_services("tenant-1")
        assert isinstance(services, list)
