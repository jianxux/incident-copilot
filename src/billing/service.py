"""Stripe billing service for subscription management."""

import structlog

from ..auth.models import PlanTier, Tenant
from ..auth.service import auth_service
from ..config import get_settings

logger = structlog.get_logger()

# Lazy import stripe to avoid import errors if not installed
stripe = None


def get_stripe():
    """Lazily import and configure Stripe."""
    global stripe
    if stripe is None:
        import stripe as _stripe

        settings = get_settings()
        _stripe.api_key = settings.stripe_api_key
        stripe = _stripe
    return stripe


class BillingService:
    """Service for managing Stripe subscriptions."""

    def __init__(self):
        self.settings = get_settings()

    @property
    def is_configured(self) -> bool:
        """Check if Stripe is configured."""
        return bool(self.settings.stripe_api_key and self.settings.stripe_publishable_key)

    def get_price_id(self, plan: PlanTier) -> str | None:
        """Get Stripe Price ID for a plan."""
        price_map = {
            PlanTier.STARTER: self.settings.stripe_price_starter,
            PlanTier.PRO: self.settings.stripe_price_pro,
            PlanTier.ENTERPRISE: self.settings.stripe_price_enterprise,
        }
        return price_map.get(plan)

    async def create_customer(self, tenant: Tenant, email: str, name: str) -> str:
        """Create a Stripe customer for a tenant."""
        if not self.is_configured:
            raise ValueError("Stripe is not configured")

        stripe = get_stripe()

        customer = stripe.Customer.create(
            email=email,
            name=name,
            metadata={
                "tenant_id": tenant.id,
                "tenant_slug": tenant.slug,
            },
        )

        # Update tenant with Stripe customer ID
        tenant.stripe_customer_id = customer.id
        tenant.updated_at = tenant.updated_at

        logger.info(
            "stripe_customer_created",
            tenant_id=tenant.id,
            customer_id=customer.id,
        )

        return customer.id

    async def create_checkout_session(
        self,
        tenant: Tenant,
        plan: PlanTier,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Create a Stripe Checkout session for upgrading to a paid plan."""
        if not self.is_configured:
            raise ValueError("Stripe is not configured")

        if plan == PlanTier.FREE:
            raise ValueError("Cannot create checkout for free plan")

        price_id = self.get_price_id(plan)
        if not price_id:
            raise ValueError(f"No price configured for plan {plan}")

        stripe = get_stripe()

        # Ensure customer exists
        if not tenant.stripe_customer_id:
            raise ValueError("Tenant has no Stripe customer")

        session = stripe.checkout.Session.create(
            customer=tenant.stripe_customer_id,
            mode="subscription",
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                },
            ],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "tenant_id": tenant.id,
                "plan": plan.value,
            },
        )

        logger.info(
            "stripe_checkout_created",
            tenant_id=tenant.id,
            plan=plan,
            session_id=session.id,
        )

        return session.url

    async def create_portal_session(self, tenant: Tenant, return_url: str) -> str:
        """Create a Stripe Customer Portal session for managing subscriptions."""
        if not self.is_configured:
            raise ValueError("Stripe is not configured")

        if not tenant.stripe_customer_id:
            raise ValueError("Tenant has no Stripe customer")

        stripe = get_stripe()

        session = stripe.billing_portal.Session.create(
            customer=tenant.stripe_customer_id,
            return_url=return_url,
        )

        return session.url

    async def handle_checkout_completed(self, session: dict) -> None:
        """Handle successful checkout completion webhook."""
        tenant_id = session.get("metadata", {}).get("tenant_id")
        plan_str = session.get("metadata", {}).get("plan")
        subscription_id = session.get("subscription")

        if not tenant_id or not plan_str:
            logger.error("checkout_completed_missing_metadata", session=session)
            return

        try:
            plan = PlanTier(plan_str)
        except ValueError:
            logger.error("checkout_completed_invalid_plan", plan=plan_str)
            return

        tenant = await auth_service.get_tenant(tenant_id)
        if not tenant:
            logger.error("checkout_completed_tenant_not_found", tenant_id=tenant_id)
            return

        # Update tenant
        tenant.stripe_subscription_id = subscription_id
        await auth_service.update_tenant_plan(tenant_id, plan)

        logger.info(
            "subscription_activated",
            tenant_id=tenant_id,
            plan=plan,
            subscription_id=subscription_id,
        )

    async def handle_subscription_updated(self, subscription: dict) -> None:
        """Handle subscription update webhook."""
        customer_id = subscription.get("customer")
        status = subscription.get("status")

        # Find tenant by customer ID
        tenant = None
        for t in auth_service._tenants.values():
            if t.stripe_customer_id == customer_id:
                tenant = t
                break

        if not tenant:
            logger.warning(
                "subscription_updated_tenant_not_found",
                customer_id=customer_id,
            )
            return

        # Handle cancellation
        if status in ["canceled", "unpaid"]:
            await auth_service.update_tenant_plan(tenant.id, PlanTier.FREE)
            tenant.stripe_subscription_id = None
            logger.info(
                "subscription_canceled",
                tenant_id=tenant.id,
                status=status,
            )

    async def handle_invoice_paid(self, invoice: dict) -> None:
        """Handle successful invoice payment webhook."""
        customer_id = invoice.get("customer")
        amount = invoice.get("amount_paid", 0) / 100  # Convert cents to dollars

        logger.info(
            "invoice_paid",
            customer_id=customer_id,
            amount=amount,
        )


# Global billing service instance
billing_service = BillingService()
