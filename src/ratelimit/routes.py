"""Admin API routes for rate limit management."""

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.auth.middleware import AuthContext, get_auth_context
from src.auth.models import UserRole

from .limiter import rate_limiter
from .models import (
    RateLimitConfig,
    RateLimitOverride,
    RateLimitResult,
    RateLimitScope,
    RateLimitStatus,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/admin/ratelimit", tags=["Rate Limiting"])


# Request/Response models
class RateLimitStatusResponse(BaseModel):
    """Response containing rate limit status for all scopes."""

    enabled: bool
    configs: dict[str, dict[str, Any]]
    overrides: list[dict[str, Any]]


class RateLimitKeyStatusRequest(BaseModel):
    """Request to get status for a specific key."""

    scope: RateLimitScope
    identifier: str


class RateLimitKeyStatusResponse(BaseModel):
    """Response containing status for a specific rate limit key."""

    key: str
    scope: str
    current_tokens: float
    capacity: int
    refill_rate: float
    last_refill: datetime
    requests_in_window: int
    utilization: float


class UpdateConfigRequest(BaseModel):
    """Request to update rate limit configuration."""

    capacity: int | None = Field(None, ge=1)
    refill_rate: float | None = Field(None, gt=0)
    enabled: bool | None = None


class SetOverrideRequest(BaseModel):
    """Request to set a rate limit override."""

    key: str = Field(..., description="The key to override (tenant ID, API key, etc.)")
    scope: RateLimitScope
    capacity: int | None = Field(None, ge=1)
    refill_rate: float | None = Field(None, gt=0)
    enabled: bool = True
    expires_at: datetime | None = None
    reason: str | None = None


class ResetKeyRequest(BaseModel):
    """Request to reset a rate limit key."""

    scope: RateLimitScope
    identifier: str


class TestLimitRequest(BaseModel):
    """Request to test rate limiting for a key."""

    scope: RateLimitScope
    identifier: str
    cost: int = 1


# Dependency to require admin role
async def require_admin(
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    """Require admin role for rate limit management."""
    if not auth.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    if not auth.user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User authentication required (API keys cannot manage rate limits)",
        )

    if auth.user.role not in [UserRole.OWNER, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    return auth


@router.get("/status", response_model=RateLimitStatusResponse)
async def get_rate_limit_status(
    auth: AuthContext = Depends(require_admin),
) -> RateLimitStatusResponse:
    """Get current rate limit configuration and status.

    Returns the current rate limit configurations for all scopes,
    active overrides, and whether rate limiting is enabled.
    """
    configs = rate_limiter.get_configs()

    config_dict = {}
    for scope, config in configs.items():
        config_dict[scope.value] = {
            "name": config.name,
            "capacity": config.capacity,
            "refill_rate": config.refill_rate,
            "tokens_per_minute": config.tokens_per_minute,
            "tokens_per_hour": config.tokens_per_hour,
            "enabled": config.enabled,
            "description": config.description,
        }

    # Get overrides
    overrides = []
    for key, override in rate_limiter._overrides.items():
        overrides.append(
            {
                "key": override.key,
                "scope": override.scope.value,
                "capacity": override.capacity,
                "refill_rate": override.refill_rate,
                "enabled": override.enabled,
                "expires_at": (
                    override.expires_at.isoformat() if override.expires_at else None
                ),
                "reason": override.reason,
                "created_at": override.created_at.isoformat(),
                "created_by": override.created_by,
            }
        )

    from src.config import get_settings

    settings = get_settings()

    return RateLimitStatusResponse(
        enabled=settings.ratelimit_enabled,
        configs=config_dict,
        overrides=overrides,
    )


@router.post("/status/key", response_model=RateLimitKeyStatusResponse)
async def get_key_status(
    request: RateLimitKeyStatusRequest,
    auth: AuthContext = Depends(require_admin),
) -> RateLimitKeyStatusResponse:
    """Get rate limit status for a specific key.

    Returns current token bucket state, utilization, and request count.
    """
    status = await rate_limiter.get_status(
        scope=request.scope,
        identifier=request.identifier,
    )

    return RateLimitKeyStatusResponse(
        key=status.key,
        scope=status.scope.value,
        current_tokens=round(status.current_tokens, 2),
        capacity=status.capacity,
        refill_rate=status.refill_rate,
        last_refill=status.last_refill,
        requests_in_window=status.requests_in_window,
        utilization=round(status.utilization, 2),
    )


@router.post("/reset/{key}")
async def reset_rate_limit(
    key: str,
    request: ResetKeyRequest,
    auth: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    """Reset rate limit for a specific key.

    This will refill the token bucket to full capacity.
    Use with caution - this allows the user/tenant/IP to
    immediately make more requests.
    """
    success = await rate_limiter.reset(
        scope=request.scope,
        identifier=request.identifier,
    )

    logger.info(
        "rate_limit_reset_by_admin",
        key=key,
        scope=request.scope.value,
        identifier=request.identifier,
        admin_user=auth.user.email if auth.user else None,
        success=success,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rate limit key not found",
        )

    return {
        "success": True,
        "message": f"Rate limit reset for {request.scope.value}:{request.identifier}",
        "scope": request.scope.value,
        "identifier": request.identifier,
    }


@router.put("/config/{scope}")
async def update_config(
    scope: str,
    request: UpdateConfigRequest,
    auth: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    """Update rate limit configuration for a scope.

    Changes apply immediately and affect all new requests.
    Existing token buckets are not reset.
    """
    try:
        scope_enum = RateLimitScope(scope)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scope: {scope}. Valid scopes: {[s.value for s in RateLimitScope]}",
        )

    config = rate_limiter.update_config(
        scope=scope_enum,
        capacity=request.capacity,
        refill_rate=request.refill_rate,
        enabled=request.enabled,
    )

    logger.info(
        "rate_limit_config_updated",
        scope=scope,
        capacity=config.capacity,
        refill_rate=config.refill_rate,
        enabled=config.enabled,
        admin_user=auth.user.email if auth.user else None,
    )

    return {
        "success": True,
        "scope": scope,
        "config": {
            "capacity": config.capacity,
            "refill_rate": config.refill_rate,
            "tokens_per_minute": config.tokens_per_minute,
            "enabled": config.enabled,
        },
    }


@router.post("/override")
async def set_override(
    request: SetOverrideRequest,
    auth: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    """Set a rate limit override for a specific key.

    Overrides allow you to give specific tenants, API keys, or IPs
    higher or lower limits than the default.
    """
    override = RateLimitOverride(
        key=request.key,
        scope=request.scope,
        capacity=request.capacity,
        refill_rate=request.refill_rate,
        enabled=request.enabled,
        expires_at=request.expires_at,
        reason=request.reason,
        created_by=auth.user.email if auth.user else None,
    )

    rate_limiter.set_override(override)

    return {
        "success": True,
        "message": f"Override set for {request.scope.value}:{request.key}",
        "override": {
            "key": override.key,
            "scope": override.scope.value,
            "capacity": override.capacity,
            "refill_rate": override.refill_rate,
            "expires_at": (
                override.expires_at.isoformat() if override.expires_at else None
            ),
        },
    }


@router.delete("/override/{scope}/{key}")
async def remove_override(
    scope: str,
    key: str,
    auth: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    """Remove a rate limit override.

    The key will revert to the default rate limit for its scope.
    """
    try:
        scope_enum = RateLimitScope(scope)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scope: {scope}",
        )

    success = rate_limiter.remove_override(scope_enum, key)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Override not found",
        )

    logger.info(
        "rate_limit_override_removed_by_admin",
        scope=scope,
        key=key,
        admin_user=auth.user.email if auth.user else None,
    )

    return {
        "success": True,
        "message": f"Override removed for {scope}:{key}",
    }


@router.post("/test")
async def test_rate_limit(
    request: TestLimitRequest,
    auth: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    """Test rate limiting for a specific key without consuming tokens.

    This is useful for debugging and verifying rate limit configuration.
    Note: This does NOT consume tokens - use for testing only.
    """
    # Get status instead of checking (to not consume tokens)
    status = await rate_limiter.get_status(
        scope=request.scope,
        identifier=request.identifier,
    )

    # Simulate what would happen
    would_allow = status.current_tokens >= request.cost
    tokens_after = max(0, status.current_tokens - request.cost)

    return {
        "scope": request.scope.value,
        "identifier": request.identifier,
        "cost": request.cost,
        "would_allow": would_allow,
        "current_tokens": round(status.current_tokens, 2),
        "tokens_after_request": (
            round(tokens_after, 2) if would_allow else status.current_tokens
        ),
        "capacity": status.capacity,
        "refill_rate": status.refill_rate,
        "utilization": round(status.utilization, 2),
    }


@router.get("/metrics")
async def get_rate_limit_metrics(
    auth: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    """Get rate limit metrics and statistics.

    Returns aggregated metrics about rate limiting usage.
    """
    # This would typically pull from Redis or a metrics store
    # For now, return basic info
    configs = rate_limiter.get_configs()

    return {
        "scopes": {
            scope.value: {
                "enabled": config.enabled,
                "capacity": config.capacity,
                "refill_rate": config.refill_rate,
                "tokens_per_minute": config.tokens_per_minute,
            }
            for scope, config in configs.items()
        },
        "overrides_count": len(rate_limiter._overrides),
        "using_redis": not rate_limiter._use_memory_fallback,
    }
