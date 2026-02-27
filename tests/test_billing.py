"""Comprehensive tests for billing module with mocked Stripe SDK."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from fastapi import HTTPException

from src.auth.models import PlanTier, Tenant, User, UserRole
from src.billing.service import BillingService
from src.billing.entitlements import (
    has_entitlement,
    get_plan_limit,
    require_entitlement,
    require_incident_quota,
    require_integration_slot,
    PLAN_ENTITLEMENTS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_settings(**overrides):
    """Create a mock settings object with Stripe keys."""
    s = MagicMock()
    s.stripe_api_key = overrides.get("stripe_api_key", "sk_test_placeholder123")
    s.stripe_publishable_key = overrides.get("stripe_publishable_key", "pk_test_placeholder123")
    s.stripe_webhook_secret = overrides.get("stripe_webhook_secret", "whsec_test_placeholder123")
    s.stripe_price_starter = overrides.get("stripe_price_starter", "price_starter_123")
    s.stripe_price_pro = overrides.get("stripe_price_pro", "price_pro_123")
    s.stripe_price_enterprise = overrides.get("stripe_price_enterprise", "price_ent_123")
    s.app_url = overrides.get("app_url", "http://localhost:8000")
    return s


def _make_tenant(**overrides) -> Tenant:
    defaults = dict(
        id="tenant_1",
        name="Acme Corp",
        slug="acme",
        plan=PlanTier.FREE,
        stripe_customer_id=None,
        stripe_subscription_id=None,
        incidents_this_month=0,
        max_incidents_per_month=5,
    )
    defaults.update(overrides)
    return Tenant(**defaults)


def _make_user(**overrides) -> User:
    defaults = dict(
        id="user_1",
        email="owner@acme.com",
        name="Owner",
        tenant_id="tenant_1",
        role=UserRole.OWNER,
    )
    defaults.update(overrides)
    return User(**defaults)


@pytest.fixture
def mock_settings():
    with patch("src.billing.service.get_settings", return_value=_make_settings()):
        yield _make_settings()


@pytest.fixture
def service(mock_settings):
    svc = BillingService()
    return svc


@pytest.fixture
def mock_stripe():
    """Patch the stripe module used inside billing service."""
    mock = MagicMock()
    with patch("src.billing.service.stripe", mock), \
         patch("src.billing.service.get_stripe", return_value=mock):
        yield mock


# ---------------------------------------------------------------------------
# BillingService Tests
# ---------------------------------------------------------------------------

class TestBillingService:
    def test_service_instantiation(self, service):
        assert service is not None

    def test_is_configured(self, service):
        assert service.is_configured is True

    def test_is_not_configured_without_keys(self):
        with patch("src.billing.service.get_settings", return_value=_make_settings(stripe_api_key="", stripe_publishable_key="")):
            svc = BillingService()
            assert svc.is_configured is False

    def test_get_price_id_pro(self, service):
        result = service.get_price_id(PlanTier.PRO)
        assert result == "price_pro_123"

    def test_get_price_id_free_returns_none(self, service):
        result = service.get_price_id(PlanTier.FREE)
        assert result is None


class TestCreateCustomer:
    @pytest.mark.asyncio
    async def test_create_customer_success(self, service, mock_stripe):
        mock_stripe.Customer.create.return_value = MagicMock(id="cus_test_123")
        tenant = _make_tenant()

        customer_id = await service.create_customer(tenant, "owner@acme.com", "Acme Corp")

        assert customer_id == "cus_test_123"
        assert tenant.stripe_customer_id == "cus_test_123"
        mock_stripe.Customer.create.assert_called_once_with(
            email="owner@acme.com",
            name="Acme Corp",
            metadata={"tenant_id": tenant.id, "tenant_slug": tenant.slug},
        )

    @pytest.mark.asyncio
    async def test_create_customer_not_configured(self):
        with patch("src.billing.service.get_settings", return_value=_make_settings(stripe_api_key="")):
            svc = BillingService()
            with pytest.raises(ValueError, match="Stripe is not configured"):
                await svc.create_customer(_make_tenant(), "a@b.com", "X")


class TestCreateCheckoutSession:
    @pytest.mark.asyncio
    async def test_checkout_success(self, service, mock_stripe):
        mock_stripe.checkout.Session.create.return_value = MagicMock(
            id="cs_test_123", url="https://checkout.stripe.com/cs_test_123"
        )
        tenant = _make_tenant(stripe_customer_id="cus_test_123")

        url = await service.create_checkout_session(
            tenant=tenant,
            plan=PlanTier.PRO,
            success_url="http://localhost/success",
            cancel_url="http://localhost/cancel",
        )

        assert url == "https://checkout.stripe.com/cs_test_123"
        mock_stripe.checkout.Session.create.assert_called_once()
        call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
        assert call_kwargs["customer"] == "cus_test_123"
        assert call_kwargs["mode"] == "subscription"
        assert call_kwargs["metadata"]["plan"] == "pro"

    @pytest.mark.asyncio
    async def test_checkout_free_plan_raises(self, service, mock_stripe):
        tenant = _make_tenant(stripe_customer_id="cus_test_123")
        with pytest.raises(ValueError, match="Cannot create checkout for free plan"):
            await service.create_checkout_session(
                tenant=tenant, plan=PlanTier.FREE,
                success_url="x", cancel_url="y",
            )

    @pytest.mark.asyncio
    async def test_checkout_no_customer_raises(self, service, mock_stripe):
        tenant = _make_tenant()  # no stripe_customer_id
        with pytest.raises(ValueError, match="no Stripe customer"):
            await service.create_checkout_session(
                tenant=tenant, plan=PlanTier.PRO,
                success_url="x", cancel_url="y",
            )


class TestCreatePortalSession:
    @pytest.mark.asyncio
    async def test_portal_success(self, service, mock_stripe):
        mock_stripe.billing_portal.Session.create.return_value = MagicMock(
            url="https://billing.stripe.com/portal/sess_123"
        )
        tenant = _make_tenant(stripe_customer_id="cus_test_123")

        url = await service.create_portal_session(tenant, return_url="http://localhost/billing")

        assert "billing.stripe.com" in url
        mock_stripe.billing_portal.Session.create.assert_called_once_with(
            customer="cus_test_123",
            return_url="http://localhost/billing",
        )

    @pytest.mark.asyncio
    async def test_portal_no_customer_raises(self, service, mock_stripe):
        tenant = _make_tenant()
        with pytest.raises(ValueError, match="no Stripe customer"):
            await service.create_portal_session(tenant, return_url="http://localhost")


class TestWebhookHandlers:
    @pytest.mark.asyncio
    async def test_handle_checkout_completed(self, service, mock_stripe):
        tenant = _make_tenant()

        with patch("src.billing.service.auth_service") as mock_auth:
            mock_auth.get_tenant = AsyncMock(return_value=tenant)
            mock_auth.update_tenant_plan = AsyncMock()

            session_data = {
                "metadata": {"tenant_id": "tenant_1", "plan": "pro"},
                "subscription": "sub_test_123",
            }

            await service.handle_checkout_completed(session_data)

            mock_auth.update_tenant_plan.assert_called_once_with("tenant_1", PlanTier.PRO)
            assert tenant.stripe_subscription_id == "sub_test_123"

    @pytest.mark.asyncio
    async def test_handle_checkout_completed_missing_metadata(self, service):
        # Should not raise, just log and return
        await service.handle_checkout_completed({"metadata": {}})

    @pytest.mark.asyncio
    async def test_handle_checkout_completed_invalid_plan(self, service):
        await service.handle_checkout_completed({
            "metadata": {"tenant_id": "t1", "plan": "nonexistent"},
        })

    @pytest.mark.asyncio
    async def test_handle_invoice_paid(self, service):
        # Should not raise
        await service.handle_invoice_paid({
            "customer": "cus_test_123",
            "amount_paid": 4900,
        })

    @pytest.mark.asyncio
    async def test_handle_subscription_updated_cancellation(self, service):
        tenant = _make_tenant(
            stripe_customer_id="cus_test_123",
            stripe_subscription_id="sub_test_123",
            plan=PlanTier.PRO,
        )

        with patch("src.billing.service.auth_service") as mock_auth:
            mock_auth._tenants = {"tenant_1": tenant}
            mock_auth.update_tenant_plan = AsyncMock()

            await service.handle_subscription_updated({
                "customer": "cus_test_123",
                "status": "canceled",
            })

            mock_auth.update_tenant_plan.assert_called_once_with(tenant.id, PlanTier.FREE)
            assert tenant.stripe_subscription_id is None

    @pytest.mark.asyncio
    async def test_handle_subscription_updated_unknown_customer(self, service):
        with patch("src.billing.service.auth_service") as mock_auth:
            mock_auth._tenants = {}
            # Should not raise
            await service.handle_subscription_updated({
                "customer": "cus_unknown",
                "status": "canceled",
            })


# ---------------------------------------------------------------------------
# Webhook Endpoint Tests
# ---------------------------------------------------------------------------

class TestWebhookEndpoint:
    @pytest.mark.asyncio
    async def test_webhook_valid_signature(self, mock_stripe, mock_settings):
        from src.billing.routes import stripe_webhook

        mock_stripe.Webhook.construct_event.return_value = {
            "type": "invoice.paid",
            "data": {"object": {"customer": "cus_123", "amount_paid": 4900}},
        }

        request = MagicMock()
        request.body = AsyncMock(return_value=b'{"type":"invoice.paid"}')
        request.headers = {"stripe-signature": "t=123,v1=abc"}

        with patch("src.billing.routes.billing_service") as mock_svc, \
             patch("src.billing.routes.get_settings", return_value=mock_settings):
            mock_svc.is_configured = True
            mock_svc.handle_invoice_paid = AsyncMock()

            result = await stripe_webhook(request)
            assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_webhook_missing_signature(self, mock_settings):
        from src.billing.routes import stripe_webhook

        request = MagicMock()
        request.body = AsyncMock(return_value=b'{}')
        request.headers = {}

        with patch("src.billing.routes.billing_service") as mock_svc, \
             patch("src.billing.routes.get_settings", return_value=mock_settings):
            mock_svc.is_configured = True

            with pytest.raises(HTTPException) as exc_info:
                await stripe_webhook(request)
            assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Entitlements Tests
# ---------------------------------------------------------------------------

class TestEntitlements:
    def test_free_plan_entitlements(self):
        assert has_entitlement(PlanTier.FREE, "basic_context")
        assert not has_entitlement(PlanTier.FREE, "ai_verdicts")
        assert not has_entitlement(PlanTier.FREE, "sso")

    def test_pro_plan_entitlements(self):
        assert has_entitlement(PlanTier.PRO, "basic_context")
        assert has_entitlement(PlanTier.PRO, "ai_verdicts")
        assert has_entitlement(PlanTier.PRO, "unlimited_incidents")
        assert has_entitlement(PlanTier.PRO, "all_integrations")
        assert not has_entitlement(PlanTier.PRO, "sso")
        assert not has_entitlement(PlanTier.PRO, "audit_logs")

    def test_enterprise_plan_entitlements(self):
        assert has_entitlement(PlanTier.ENTERPRISE, "ai_verdicts")
        assert has_entitlement(PlanTier.ENTERPRISE, "sso")
        assert has_entitlement(PlanTier.ENTERPRISE, "audit_logs")
        assert has_entitlement(PlanTier.ENTERPRISE, "sla")

    def test_plan_limits_free(self):
        assert get_plan_limit(PlanTier.FREE, "max_incidents_per_month") == 5
        assert get_plan_limit(PlanTier.FREE, "max_integrations") == 1

    def test_plan_limits_pro_unlimited(self):
        assert get_plan_limit(PlanTier.PRO, "max_incidents_per_month") == -1
        assert get_plan_limit(PlanTier.PRO, "max_integrations") == -1


class TestEntitlementMiddleware:
    @pytest.mark.asyncio
    async def test_require_entitlement_passes_for_pro(self):
        from src.auth.middleware import AuthContext

        tenant = _make_tenant(plan=PlanTier.PRO)
        auth = AuthContext(user=_make_user(), tenant=tenant)

        checker = require_entitlement("ai_verdicts")
        result = await checker(auth=auth)
        assert result.tenant.plan == PlanTier.PRO

    @pytest.mark.asyncio
    async def test_require_entitlement_blocks_free(self):
        from src.auth.middleware import AuthContext

        tenant = _make_tenant(plan=PlanTier.FREE)
        auth = AuthContext(user=_make_user(), tenant=tenant)

        checker = require_entitlement("ai_verdicts")
        with pytest.raises(HTTPException) as exc_info:
            await checker(auth=auth)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_entitlement_no_tenant(self):
        from src.auth.middleware import AuthContext

        auth = AuthContext()
        checker = require_entitlement("ai_verdicts")
        with pytest.raises(HTTPException) as exc_info:
            await checker(auth=auth)
        assert exc_info.value.status_code == 401


class TestIncidentQuotaMiddleware:
    @pytest.mark.asyncio
    async def test_quota_ok(self):
        from src.auth.middleware import AuthContext

        tenant = _make_tenant(plan=PlanTier.FREE, incidents_this_month=3)
        auth = AuthContext(user=_make_user(), tenant=tenant)

        checker = require_incident_quota()
        result = await checker(auth=auth)
        assert result is not None

    @pytest.mark.asyncio
    async def test_quota_exceeded(self):
        from src.auth.middleware import AuthContext

        tenant = _make_tenant(plan=PlanTier.FREE, incidents_this_month=5)
        auth = AuthContext(user=_make_user(), tenant=tenant)

        checker = require_incident_quota()
        with pytest.raises(HTTPException) as exc_info:
            await checker(auth=auth)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_quota_unlimited_for_pro(self):
        from src.auth.middleware import AuthContext

        tenant = _make_tenant(plan=PlanTier.PRO, incidents_this_month=9999)
        auth = AuthContext(user=_make_user(), tenant=tenant)

        checker = require_incident_quota()
        result = await checker(auth=auth)
        assert result is not None


class TestIntegrationSlotMiddleware:
    @pytest.mark.asyncio
    async def test_slot_ok(self):
        from src.auth.middleware import AuthContext

        tenant = _make_tenant(plan=PlanTier.FREE)
        auth = AuthContext(user=_make_user(), tenant=tenant)

        checker = require_integration_slot()
        result = await checker(auth=auth)
        assert result is not None

    @pytest.mark.asyncio
    async def test_slot_exceeded(self):
        from src.auth.middleware import AuthContext

        tenant = _make_tenant(plan=PlanTier.FREE, integrations={"slack": {"token": "x"}})
        auth = AuthContext(user=_make_user(), tenant=tenant)

        checker = require_integration_slot()
        with pytest.raises(HTTPException) as exc_info:
            await checker(auth=auth)
        assert exc_info.value.status_code == 403


class TestBillingRoutes:
    def test_billing_routes_registered(self):
        from src.billing.routes import router
        assert len(router.routes) > 0

    def test_plans_endpoint_has_three_tiers(self):
        from src.billing.routes import PLANS
        assert PlanTier.FREE in PLANS
        assert PlanTier.PRO in PLANS
        assert PlanTier.ENTERPRISE in PLANS
        # Starter removed from user-facing plans
        assert PlanTier.STARTER not in PLANS

    def test_free_plan_limits(self):
        from src.billing.routes import PLANS
        free = PLANS[PlanTier.FREE]
        assert free.price_monthly == 0
        assert free.max_incidents == 5
        assert free.max_integrations == 1

    def test_pro_plan_price(self):
        from src.billing.routes import PLANS
        pro = PLANS[PlanTier.PRO]
        assert pro.price_monthly == 49
        assert pro.max_incidents == -1  # unlimited
