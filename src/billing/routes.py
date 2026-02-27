"""API routes for billing and subscription management."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth.middleware import AuthContext, get_auth_context, get_current_user
from ..auth.models import PlanTier, User
from ..config import get_settings
from .service import billing_service, get_stripe

logger = structlog.get_logger()

router = APIRouter(prefix="/api/billing", tags=["billing"])


class UpgradeRequest(BaseModel):
    """Request to upgrade subscription."""

    plan: PlanTier


class PlanInfo(BaseModel):
    """Information about a pricing plan."""

    id: str
    name: str
    price_monthly: int
    max_incidents: int
    max_users: int
    max_integrations: int
    features: list[str]


# Plan definitions — three user-facing tiers
PLANS = {
    PlanTier.FREE: PlanInfo(
        id="free",
        name="Free",
        price_monthly=0,
        max_incidents=5,
        max_users=3,
        max_integrations=1,
        features=[
            "Basic context assembly",
            "Slack notifications",
            "Community support",
        ],
    ),
    PlanTier.PRO: PlanInfo(
        id="pro",
        name="Pro",
        price_monthly=49,
        max_incidents=-1,  # Unlimited
        max_users=50,
        max_integrations=-1,  # All integrations
        features=[
            "Everything in Free",
            "Unlimited incidents",
            "All integrations",
            "AI verdicts",
            "Advanced analytics",
            "Priority support",
            "30-day history",
        ],
    ),
    PlanTier.ENTERPRISE: PlanInfo(
        id="enterprise",
        name="Enterprise",
        price_monthly=-1,  # Custom pricing
        max_incidents=-1,
        max_users=-1,
        max_integrations=-1,
        features=[
            "Everything in Pro",
            "SSO / SAML",
            "Audit logs",
            "SLA guarantees",
            "Dedicated support",
            "On-premise option",
        ],
    ),
}


@router.get("/plans")
async def list_plans() -> list[PlanInfo]:
    """List all available plans."""
    return list(PLANS.values())


@router.get("/current")
async def get_current_subscription(
    auth: AuthContext = Depends(get_auth_context),
):
    """Get current subscription info for the tenant."""
    if not auth.tenant:
        raise HTTPException(status_code=401, detail="Authentication required")

    tenant = auth.tenant
    plan_info = PLANS.get(tenant.plan, PLANS[PlanTier.FREE])

    return {
        "plan": tenant.plan,
        "plan_info": plan_info,
        "usage": {
            "incidents_this_month": tenant.incidents_this_month,
            "max_incidents": tenant.max_incidents_per_month,
            "billing_cycle_start": tenant.billing_cycle_start.isoformat(),
        },
        "has_stripe_customer": bool(tenant.stripe_customer_id),
        "has_subscription": bool(tenant.stripe_subscription_id),
    }


@router.post("/checkout")
async def create_checkout(
    request: UpgradeRequest,
    auth: AuthContext = Depends(get_auth_context),
    user: User = Depends(get_current_user),
):
    """Create a Stripe Checkout session to upgrade to a paid plan."""
    if not billing_service.is_configured:
        raise HTTPException(
            status_code=501,
            detail="Billing is not configured",
        )

    if not auth.tenant:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not user.can_manage_billing():
        raise HTTPException(
            status_code=403,
            detail="Only the owner can manage billing",
        )

    if request.plan == PlanTier.FREE:
        raise HTTPException(
            status_code=400,
            detail="Cannot checkout for free plan",
        )

    if request.plan == PlanTier.ENTERPRISE:
        raise HTTPException(
            status_code=400,
            detail="Contact sales for Enterprise plan",
        )

    settings = get_settings()
    tenant = auth.tenant

    # Create Stripe customer if needed
    if not tenant.stripe_customer_id:
        await billing_service.create_customer(tenant, user.email, user.name)

    # Create checkout session
    checkout_url = await billing_service.create_checkout_session(
        tenant=tenant,
        plan=request.plan,
        success_url=f"{settings.app_url}/dashboard/billing/success",
        cancel_url=f"{settings.app_url}/dashboard/billing",
    )

    return {"checkout_url": checkout_url}


@router.post("/portal")
async def create_portal_session(
    auth: AuthContext = Depends(get_auth_context),
    user: User = Depends(get_current_user),
):
    """Create a Stripe Customer Portal session to manage subscription."""
    if not billing_service.is_configured:
        raise HTTPException(
            status_code=501,
            detail="Billing is not configured",
        )

    if not auth.tenant:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not user.can_manage_billing():
        raise HTTPException(
            status_code=403,
            detail="Only the owner can manage billing",
        )

    if not auth.tenant.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No billing account set up",
        )

    settings = get_settings()

    portal_url = await billing_service.create_portal_session(
        tenant=auth.tenant,
        return_url=f"{settings.app_url}/dashboard/billing",
    )

    return {"portal_url": portal_url}


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    if not billing_service.is_configured:
        raise HTTPException(status_code=501, detail="Billing not configured")

    settings = get_settings()
    stripe = get_stripe()

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing signature")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.stripe_webhook_secret,
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the event
    event_type = event["type"]
    data = event["data"]["object"]

    logger.info("stripe_webhook_received", event_type=event_type)

    if event_type == "checkout.session.completed":
        await billing_service.handle_checkout_completed(data)
    elif event_type == "customer.subscription.updated":
        await billing_service.handle_subscription_updated(data)
    elif event_type == "customer.subscription.deleted":
        await billing_service.handle_subscription_updated(data)
    elif event_type == "invoice.paid":
        await billing_service.handle_invoice_paid(data)

    return {"status": "ok"}
