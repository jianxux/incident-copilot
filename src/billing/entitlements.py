"""Entitlement middleware that gates features based on tenant plan."""

from functools import wraps
from collections.abc import Callable

import structlog
from fastapi import Depends, HTTPException, status

from ..auth.middleware import AuthContext, get_auth_context
from ..auth.models import PlanTier

logger = structlog.get_logger()

# Feature entitlements per plan tier
PLAN_ENTITLEMENTS: dict[PlanTier, set[str]] = {
    PlanTier.FREE: {
        "basic_context",
        "slack_notifications",
    },
    PlanTier.STARTER: {
        "basic_context",
        "slack_notifications",
        "ai_verdicts",
        "all_integrations",
    },
    PlanTier.PRO: {
        "basic_context",
        "slack_notifications",
        "ai_verdicts",
        "unlimited_incidents",
        "all_integrations",
    },
    PlanTier.ENTERPRISE: {
        "basic_context",
        "slack_notifications",
        "ai_verdicts",
        "unlimited_incidents",
        "all_integrations",
        "sso",
        "audit_logs",
        "sla",
    },
}

# Plan limits for incidents and integrations
PLAN_LIMITS = {
    PlanTier.FREE: {"max_incidents_per_month": 5, "max_integrations": 1},
    PlanTier.STARTER: {"max_incidents_per_month": 500, "max_integrations": 5},
    PlanTier.PRO: {"max_incidents_per_month": -1, "max_integrations": -1},  # unlimited
    PlanTier.ENTERPRISE: {"max_incidents_per_month": -1, "max_integrations": -1},
}


def has_entitlement(plan: PlanTier, feature: str) -> bool:
    """Check if a plan has a specific feature entitlement."""
    entitlements = PLAN_ENTITLEMENTS.get(plan, set())
    return feature in entitlements


def get_plan_limit(plan: PlanTier, limit_key: str) -> int:
    """Get a numeric limit for a plan. Returns -1 for unlimited."""
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS[PlanTier.FREE])
    return limits.get(limit_key, 0)


def require_entitlement(feature: str):
    """
    FastAPI dependency factory that checks if the current tenant's plan
    includes the specified feature entitlement.

    Usage:
        @router.get("/ai-verdict", dependencies=[Depends(require_entitlement("ai_verdicts"))])
        async def get_ai_verdict(): ...
    """

    async def _check_entitlement(
        auth: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        if not auth.tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        plan = auth.tenant.plan
        if not has_entitlement(plan, feature):
            logger.warning(
                "entitlement_denied",
                tenant_id=auth.tenant.id,
                plan=plan,
                feature=feature,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Feature '{feature}' requires a higher plan. Current plan: {plan}",
            )

        return auth

    return _check_entitlement


def require_incident_quota():
    """
    FastAPI dependency that checks if the tenant has remaining incident quota.
    """

    async def _check_quota(
        auth: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        if not auth.tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        tenant = auth.tenant
        max_incidents = get_plan_limit(tenant.plan, "max_incidents_per_month")

        # -1 means unlimited
        if max_incidents != -1 and tenant.incidents_this_month >= max_incidents:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Monthly incident limit reached ({max_incidents}). Upgrade your plan for more.",
            )

        return auth

    return _check_quota


def require_integration_slot():
    """
    FastAPI dependency that checks if the tenant can add more integrations.
    """

    async def _check_integration_slot(
        auth: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        if not auth.tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        tenant = auth.tenant
        max_integrations = get_plan_limit(tenant.plan, "max_integrations")
        current_integrations = len(tenant.integrations)

        if max_integrations != -1 and current_integrations >= max_integrations:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Integration limit reached ({max_integrations}). Upgrade your plan for more.",
            )

        return auth

    return _check_integration_slot
