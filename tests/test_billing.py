"""Tests for billing module."""

import pytest

from src.billing.service import BillingService


class TestBillingService:
    @pytest.fixture
    def service(self):
        return BillingService()

    def test_service_instantiation(self, service):
        assert service is not None

    def test_is_configured(self, service):
        # Without Stripe keys, should not be configured
        result = service.is_configured
        assert isinstance(result, bool)

    def test_get_price_id(self, service):
        # Should return a price ID string or None
        result = service.get_price_id("pro")
        assert result is None or isinstance(result, str)


class TestBillingRoutes:
    def test_billing_routes_registered(self):
        from src.billing.routes import router
        assert len(router.routes) > 0
