"""FastAPI middleware for API rate limiting."""

import re
from typing import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from src.config import get_settings

from .limiter import rate_limiter
from .models import RateLimitResult, RateLimitScope

logger = structlog.get_logger()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces rate limits on API requests.

    Supports multiple rate limiting scopes:
    - Per-IP: Limits based on client IP address
    - Per-API-Key: Limits based on API key
    - Per-Tenant: Limits based on tenant ID
    - Per-User: Limits based on user ID
    - Per-Endpoint: Different limits for different endpoints

    The middleware checks all applicable scopes and enforces
    the most restrictive limit that applies.
    """

    def __init__(
        self,
        app: ASGIApp,
        exclude_paths: list[str] | None = None,
        enabled: bool = True,
    ):
        super().__init__(app)
        settings = get_settings()

        self.enabled = enabled and settings.ratelimit_enabled
        self.exclude_paths = exclude_paths or settings.ratelimit_exclude_paths

        # Compile exclude patterns for performance
        self._exclude_patterns = [
            re.compile(p.replace("*", ".*")) for p in self.exclude_paths
        ]

        logger.info(
            "rate_limit_middleware_initialized",
            enabled=self.enabled,
            exclude_paths=self.exclude_paths,
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request and enforce rate limits."""
        # Skip if disabled
        if not self.enabled:
            return await call_next(request)

        # Check if path should be excluded
        path = request.url.path
        if self._should_exclude(path):
            return await call_next(request)

        # Extract identifiers for rate limiting
        ip_address = self._get_client_ip(request)
        api_key_id = self._get_api_key_id(request)
        tenant_id = self._get_tenant_id(request)
        user_id = self._get_user_id(request)

        # Build list of checks to perform
        checks: list[tuple[RateLimitScope, str]] = []

        # Always check IP
        if ip_address:
            checks.append((RateLimitScope.IP, ip_address))

        # Check API key if present
        if api_key_id:
            checks.append((RateLimitScope.API_KEY, api_key_id))

        # Check tenant if authenticated
        if tenant_id:
            checks.append((RateLimitScope.TENANT, tenant_id))

        # Check user if authenticated
        if user_id:
            checks.append((RateLimitScope.USER, user_id))

        # Perform rate limit check
        result = await rate_limiter.check_multiple(
            checks=checks,
            endpoint=path,
            method=request.method,
        )

        # If denied, return 429
        if not result.allowed:
            return self._create_rate_limit_response(result, request)

        # Process request and add rate limit headers to response
        response = await call_next(request)

        # Add rate limit headers
        for header, value in result.to_headers().items():
            response.headers[header] = value

        return response

    def _should_exclude(self, path: str) -> bool:
        """Check if path should be excluded from rate limiting."""
        for pattern in self._exclude_patterns:
            if pattern.match(path):
                return True
        return False

    def _get_client_ip(self, request: Request) -> str | None:
        """Extract client IP, considering proxy headers."""
        # Check common proxy headers
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take first IP (original client)
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to direct connection
        if request.client:
            return request.client.host

        return None

    def _get_api_key_id(self, request: Request) -> str | None:
        """Extract API key ID from request state (set by auth middleware)."""
        # Check request state (set by auth middleware)
        if hasattr(request.state, "api_key_id"):
            return request.state.api_key_id

        # Check for auth context
        if hasattr(request.state, "auth"):
            auth = request.state.auth
            if hasattr(auth, "api_key_id"):
                return auth.api_key_id

        # Check scope (ASGI middleware)
        if "auth" in request.scope:
            auth = request.scope["auth"]
            if hasattr(auth, "api_key_id"):
                return auth.api_key_id

        return None

    def _get_tenant_id(self, request: Request) -> str | None:
        """Extract tenant ID from request."""
        # Check request state
        if hasattr(request.state, "tenant_id"):
            return request.state.tenant_id

        # Check auth context
        if hasattr(request.state, "auth"):
            auth = request.state.auth
            if hasattr(auth, "tenant_id"):
                return auth.tenant_id
            if hasattr(auth, "tenant") and auth.tenant:
                return auth.tenant.id

        # Check scope
        if "auth" in request.scope:
            auth = request.scope["auth"]
            if hasattr(auth, "tenant_id"):
                return auth.tenant_id
            if hasattr(auth, "tenant") and auth.tenant:
                return auth.tenant.id

        return None

    def _get_user_id(self, request: Request) -> str | None:
        """Extract user ID from request."""
        # Check request state
        if hasattr(request.state, "user_id"):
            return request.state.user_id

        # Check auth context
        if hasattr(request.state, "auth"):
            auth = request.state.auth
            if hasattr(auth, "user_id"):
                return auth.user_id
            if hasattr(auth, "user") and auth.user:
                return auth.user.id

        # Check scope
        if "auth" in request.scope:
            auth = request.scope["auth"]
            if hasattr(auth, "user_id"):
                return auth.user_id
            if hasattr(auth, "user") and auth.user:
                return auth.user.id

        return None

    def _create_rate_limit_response(
        self,
        result: RateLimitResult,
        request: Request,
    ) -> Response:
        """Create a 429 Too Many Requests response."""
        logger.warning(
            "rate_limit_exceeded_response",
            path=request.url.path,
            method=request.method,
            scope=result.scope.value,
            remaining=result.remaining,
            limit=result.limit,
            retry_after=result.retry_after,
        )

        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "message": "Too many requests. Please slow down.",
                "scope": result.scope.value,
                "limit": result.limit,
                "remaining": result.remaining,
                "retry_after": result.retry_after,
            },
            headers=result.to_headers(),
        )


def add_rate_limit_middleware(
    app: ASGIApp,
    exclude_paths: list[str] | None = None,
) -> ASGIApp:
    """Add rate limiting middleware to a FastAPI application.

    Usage:
        from fastapi import FastAPI
        from src.ratelimit.middleware import add_rate_limit_middleware

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware)
        # or
        app = add_rate_limit_middleware(app)
    """
    settings = get_settings()
    if not settings.ratelimit_enabled:
        return app

    return RateLimitMiddleware(app, exclude_paths=exclude_paths)


# Decorator for per-endpoint rate limiting
def rate_limit(
    capacity: int = 10,
    refill_rate: float = 1.0,
    scope: RateLimitScope = RateLimitScope.IP,
    cost: int = 1,
) -> Callable:
    """Decorator to apply custom rate limits to specific endpoints.

    This decorator can be used to override the default rate limits
    for specific endpoints that need stricter or more permissive limits.

    Usage:
        @router.post("/expensive-operation")
        @rate_limit(capacity=5, refill_rate=0.1)  # 5 requests, 1 refill per 10 seconds
        async def expensive_operation():
            ...

        @router.get("/high-volume")
        @rate_limit(capacity=1000, refill_rate=100)  # Very permissive
        async def high_volume_endpoint():
            ...
    """

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            # Get request from kwargs
            request: Request | None = kwargs.get("request")

            if request:
                # Get identifier based on scope
                identifier = None
                if scope == RateLimitScope.IP:
                    if request.client:
                        identifier = request.client.host
                elif scope == RateLimitScope.API_KEY:
                    if hasattr(request.state, "api_key_id"):
                        identifier = request.state.api_key_id
                elif scope == RateLimitScope.TENANT:
                    if hasattr(request.state, "tenant_id"):
                        identifier = request.state.tenant_id
                elif scope == RateLimitScope.USER:
                    if hasattr(request.state, "user_id"):
                        identifier = request.state.user_id

                if identifier:
                    # Create a unique key for this endpoint
                    endpoint_key = f"{func.__module__}.{func.__name__}:{identifier}"

                    result = await rate_limiter.check(
                        scope=scope,
                        identifier=endpoint_key,
                        cost=cost,
                        endpoint=request.url.path,
                        method=request.method,
                    )

                    if not result.allowed:
                        return JSONResponse(
                            status_code=429,
                            content={
                                "error": "rate_limit_exceeded",
                                "message": "Rate limit exceeded for this endpoint",
                                "retry_after": result.retry_after,
                            },
                            headers=result.to_headers(),
                        )

            return await func(*args, **kwargs)

        # Preserve function metadata
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator
