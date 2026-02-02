"""Health check endpoints for Incident Copilot.

Provides comprehensive health status for the application and its dependencies.
"""

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from ..config import get_settings

logger = structlog.get_logger()
router = APIRouter(tags=["health"])


class HealthStatus(str, Enum):
    """Health status enum."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Health status of a single component."""

    name: str
    status: HealthStatus
    latency_ms: float | None = None
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Overall health response."""

    status: HealthStatus
    timestamp: str
    version: str
    uptime_seconds: float | None = None
    components: list[ComponentHealth] = Field(default_factory=list)


# Track app start time for uptime
_app_start_time: datetime | None = None


def set_app_start_time() -> None:
    """Set the application start time (call on startup)."""
    global _app_start_time
    _app_start_time = datetime.now(timezone.utc)


def get_uptime_seconds() -> float | None:
    """Get application uptime in seconds."""
    if _app_start_time is None:
        return None
    return (datetime.now(timezone.utc) - _app_start_time).total_seconds()


async def check_redis_health() -> ComponentHealth:
    """Check Redis connectivity."""
    import time

    settings = get_settings()
    start = time.perf_counter()

    try:
        import redis.asyncio as redis

        client = redis.from_url(settings.redis_url, socket_timeout=5.0)
        await client.ping()
        await client.close()

        latency = (time.perf_counter() - start) * 1000

        return ComponentHealth(
            name="redis",
            status=HealthStatus.HEALTHY,
            latency_ms=round(latency, 2),
            message="Connected",
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            name="redis",
            status=HealthStatus.UNHEALTHY,
            latency_ms=round(latency, 2),
            message=f"Connection failed: {str(e)[:100]}",
        )


async def check_database_health() -> ComponentHealth:
    """Check PostgreSQL connectivity."""
    import time

    settings = get_settings()
    start = time.perf_counter()

    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(settings.database_url, pool_pre_ping=True)

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        await engine.dispose()

        latency = (time.perf_counter() - start) * 1000

        return ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            latency_ms=round(latency, 2),
            message="Connected",
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            latency_ms=round(latency, 2),
            message=f"Connection failed: {str(e)[:100]}",
        )


async def check_pagerduty_health() -> ComponentHealth:
    """Check PagerDuty API connectivity."""
    import time

    settings = get_settings()

    if not settings.pagerduty_api_key:
        return ComponentHealth(
            name="pagerduty",
            status=HealthStatus.DEGRADED,
            message="Not configured",
        )

    start = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.pagerduty.com/abilities",
                headers={
                    "Authorization": f"Token token={settings.pagerduty_api_key}",
                    "Accept": "application/vnd.pagerduty+json;version=2",
                },
            )
            response.raise_for_status()

        latency = (time.perf_counter() - start) * 1000

        return ComponentHealth(
            name="pagerduty",
            status=HealthStatus.HEALTHY,
            latency_ms=round(latency, 2),
            message="API accessible",
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            name="pagerduty",
            status=HealthStatus.UNHEALTHY,
            latency_ms=round(latency, 2),
            message=f"API error: {str(e)[:100]}",
        )


async def check_github_health() -> ComponentHealth:
    """Check GitHub API connectivity."""
    import time

    settings = get_settings()

    if not settings.github_token:
        return ComponentHealth(
            name="github",
            status=HealthStatus.DEGRADED,
            message="Not configured",
        )

    start = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.github.com/rate_limit",
                headers={
                    "Authorization": f"token {settings.github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            response.raise_for_status()
            data = response.json()

        latency = (time.perf_counter() - start) * 1000
        rate_limit = data.get("rate", {})

        return ComponentHealth(
            name="github",
            status=HealthStatus.HEALTHY,
            latency_ms=round(latency, 2),
            message="API accessible",
            details={
                "rate_limit_remaining": rate_limit.get("remaining"),
                "rate_limit_limit": rate_limit.get("limit"),
            },
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            name="github",
            status=HealthStatus.UNHEALTHY,
            latency_ms=round(latency, 2),
            message=f"API error: {str(e)[:100]}",
        )


async def check_datadog_health() -> ComponentHealth:
    """Check Datadog API connectivity."""
    import time

    settings = get_settings()

    if not settings.datadog_api_key or not settings.datadog_app_key:
        return ComponentHealth(
            name="datadog",
            status=HealthStatus.DEGRADED,
            message="Not configured",
        )

    start = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://api.{settings.datadog_site}/api/v1/validate",
                headers={
                    "DD-API-KEY": settings.datadog_api_key,
                    "DD-APPLICATION-KEY": settings.datadog_app_key,
                },
            )
            response.raise_for_status()

        latency = (time.perf_counter() - start) * 1000

        return ComponentHealth(
            name="datadog",
            status=HealthStatus.HEALTHY,
            latency_ms=round(latency, 2),
            message="API accessible",
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            name="datadog",
            status=HealthStatus.UNHEALTHY,
            latency_ms=round(latency, 2),
            message=f"API error: {str(e)[:100]}",
        )


async def check_slack_health() -> ComponentHealth:
    """Check Slack API connectivity."""
    import time

    settings = get_settings()

    if not settings.slack_bot_token:
        return ComponentHealth(
            name="slack",
            status=HealthStatus.DEGRADED,
            message="Not configured",
        )

    start = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://slack.com/api/auth.test",
                headers={
                    "Authorization": f"Bearer {settings.slack_bot_token}",
                },
            )
            data = response.json()

        latency = (time.perf_counter() - start) * 1000

        if data.get("ok"):
            return ComponentHealth(
                name="slack",
                status=HealthStatus.HEALTHY,
                latency_ms=round(latency, 2),
                message="API accessible",
                details={
                    "bot_user": data.get("user"),
                    "team": data.get("team"),
                },
            )
        else:
            return ComponentHealth(
                name="slack",
                status=HealthStatus.UNHEALTHY,
                latency_ms=round(latency, 2),
                message=f"Auth failed: {data.get('error')}",
            )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            name="slack",
            status=HealthStatus.UNHEALTHY,
            latency_ms=round(latency, 2),
            message=f"API error: {str(e)[:100]}",
        )


async def check_anthropic_health() -> ComponentHealth:
    """Check Anthropic API connectivity."""
    import time

    settings = get_settings()

    if not settings.anthropic_api_key:
        return ComponentHealth(
            name="anthropic",
            status=HealthStatus.DEGRADED,
            message="Not configured",
        )

    start = time.perf_counter()

    try:
        # Just check if the API key format is valid by making a minimal request
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Use a simple models list endpoint to verify auth
            response = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            # 200 or 401 both tell us if the key is valid
            if response.status_code == 401:
                raise ValueError("Invalid API key")
            response.raise_for_status()

        latency = (time.perf_counter() - start) * 1000

        return ComponentHealth(
            name="anthropic",
            status=HealthStatus.HEALTHY,
            latency_ms=round(latency, 2),
            message="API accessible",
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            name="anthropic",
            status=HealthStatus.UNHEALTHY,
            latency_ms=round(latency, 2),
            message=f"API error: {str(e)[:100]}",
        )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Comprehensive health check",
    description="Check health of the application and all dependencies",
)
async def health_check(
    response: Response,
    full: bool = False,
) -> HealthResponse:
    """Comprehensive health check endpoint.

    Args:
        full: If True, check all external dependencies (slower).
              If False, just check core components (fast).

    Returns:
        Health status of all components.
    """
    components = []

    if full:
        # Run all health checks in parallel
        checks = await asyncio.gather(
            check_redis_health(),
            check_database_health(),
            check_pagerduty_health(),
            check_github_health(),
            check_datadog_health(),
            check_slack_health(),
            check_anthropic_health(),
            return_exceptions=True,
        )

        for check in checks:
            if isinstance(check, Exception):
                components.append(
                    ComponentHealth(
                        name="unknown",
                        status=HealthStatus.UNHEALTHY,
                        message=str(check)[:100],
                    )
                )
            else:
                components.append(check)
    else:
        # Quick health check - just Redis and DB
        checks = await asyncio.gather(
            check_redis_health(),
            check_database_health(),
            return_exceptions=True,
        )

        for check in checks:
            if isinstance(check, Exception):
                components.append(
                    ComponentHealth(
                        name="unknown",
                        status=HealthStatus.UNHEALTHY,
                        message=str(check)[:100],
                    )
                )
            else:
                components.append(check)

    # Determine overall status
    statuses = [c.status for c in components]

    if all(s == HealthStatus.HEALTHY for s in statuses):
        overall_status = HealthStatus.HEALTHY
    elif any(s == HealthStatus.UNHEALTHY for s in statuses):
        overall_status = HealthStatus.UNHEALTHY
    else:
        overall_status = HealthStatus.DEGRADED

    # Set HTTP status code based on health
    if overall_status == HealthStatus.UNHEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif overall_status == HealthStatus.DEGRADED:
        response.status_code = status.HTTP_200_OK  # Still operational

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="0.1.0",
        uptime_seconds=get_uptime_seconds(),
        components=components,
    )


@router.get(
    "/health/live",
    summary="Liveness probe",
    description="Simple liveness check for Kubernetes",
)
async def liveness() -> dict:
    """Kubernetes liveness probe.

    Returns 200 if the application is running.
    This should always succeed unless the app is completely broken.
    """
    return {"status": "alive"}


@router.get(
    "/health/ready",
    summary="Readiness probe",
    description="Check if the application is ready to receive traffic",
)
async def readiness(response: Response) -> dict:
    """Kubernetes readiness probe.

    Returns 200 if the application is ready to serve traffic.
    Checks core dependencies (Redis, DB).
    """
    redis_health = await check_redis_health()
    db_health = await check_database_health()

    if (
        redis_health.status == HealthStatus.HEALTHY
        and db_health.status == HealthStatus.HEALTHY
    ):
        return {"status": "ready"}

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "not_ready",
        "redis": redis_health.status.value,
        "database": db_health.status.value,
    }
