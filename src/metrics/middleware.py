"""HTTP metrics middleware for FastAPI."""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from . import (
    ACTIVE_CONNECTIONS,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to track HTTP request metrics."""

    def __init__(
        self,
        app: ASGIApp,
        exclude_paths: set[str] | None = None,
    ):
        super().__init__(app)
        # Paths to exclude from metrics (e.g., /metrics itself, health checks)
        self.exclude_paths = exclude_paths or {"/metrics", "/health"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Normalize endpoint for cardinality control
        # Replace path parameters with placeholders
        endpoint = self._normalize_path(request.url.path)
        method = request.method

        # Track active connections
        ACTIVE_CONNECTIONS.inc()

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = str(response.status_code)
        except Exception as e:
            status_code = "500"
            raise
        finally:
            # Record metrics
            duration = time.perf_counter() - start_time

            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
            ).inc()

            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                endpoint=endpoint,
            ).observe(duration)

            ACTIVE_CONNECTIONS.dec()

        return response

    def _normalize_path(self, path: str) -> str:
        """Normalize URL paths to reduce cardinality.

        Replace dynamic path segments (UUIDs, IDs) with placeholders.
        """
        import re

        # Replace UUIDs
        path = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{uuid}",
            path,
            flags=re.IGNORECASE,
        )

        # Replace numeric IDs
        path = re.sub(r"/\d+(?=/|$)", "/{id}", path)

        # Replace tenant IDs (commonly prefixed paths)
        path = re.sub(r"/tenants/[^/]+", "/tenants/{tenant_id}", path)
        path = re.sub(r"/incidents/[^/]+", "/incidents/{incident_id}", path)
        path = re.sub(r"/users/[^/]+", "/users/{user_id}", path)

        return path
