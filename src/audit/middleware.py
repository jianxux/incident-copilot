"""FastAPI middleware for automatic audit logging of API requests."""

import secrets
import time
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from src.config import get_settings

from .logger import audit_logger
from .models import EventCategory, EventType, Outcome


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware that automatically logs API requests for audit trail.

    Captures request/response details, extracts actor from auth context,
    and logs to the audit store.
    """

    def __init__(
        self,
        app: ASGIApp,
        exclude_paths: list[str] | None = None,
        log_all_requests: bool = False,
    ):
        super().__init__(app)
        settings = get_settings()
        self.exclude_paths = exclude_paths or settings.audit_exclude_paths
        self.log_all_requests = log_all_requests or settings.audit_log_all_requests
        self.enabled = settings.audit_enabled

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request and log audit event if applicable."""
        # Skip if audit disabled
        if not self.enabled:
            return await call_next(request)

        # Check if path should be excluded
        path = request.url.path
        if self._should_exclude(path):
            return await call_next(request)

        # Generate request ID if not present
        request_id = request.headers.get("X-Request-ID") or secrets.token_urlsafe(8)

        # Extract request info
        ip_address = self._get_client_ip(request)
        user_agent = request.headers.get("User-Agent")

        # Time the request
        start_time = time.perf_counter()

        # Process request
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log audit event
            await self._log_request(
                request=request,
                response=response,
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                duration_ms=duration_ms,
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log error
            await self._log_error(
                request=request,
                error=e,
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                duration_ms=duration_ms,
            )
            raise

    def _should_exclude(self, path: str) -> bool:
        """Check if path should be excluded from audit logging."""
        for excluded in self.exclude_paths:
            if path == excluded or path.startswith(excluded.rstrip("/") + "/"):
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

    def _extract_actor(self, request: Request) -> dict[str, Any]:
        """Extract actor information from request state/auth context."""
        actor: dict[str, Any] = {
            "tenant_id": None,
            "user_id": None,
            "user_email": None,
            "api_key_id": None,
            "session_id": None,
        }

        # Check request state for auth info (set by auth middleware)
        if hasattr(request.state, "user"):
            user = request.state.user
            if hasattr(user, "tenant_id"):
                actor["tenant_id"] = user.tenant_id
            if hasattr(user, "id"):
                actor["user_id"] = user.id
            if hasattr(user, "email"):
                actor["user_email"] = user.email

        if hasattr(request.state, "tenant_id"):
            actor["tenant_id"] = request.state.tenant_id

        if hasattr(request.state, "api_key_id"):
            actor["api_key_id"] = request.state.api_key_id

        if hasattr(request.state, "session_id"):
            actor["session_id"] = request.state.session_id

        # Check for tenant in path parameters
        if not actor["tenant_id"]:
            # Try to extract from path (e.g., /api/v1/tenants/{tenant_id}/...)
            path_parts = request.url.path.split("/")
            if "tenants" in path_parts:
                idx = path_parts.index("tenants")
                if idx + 1 < len(path_parts):
                    actor["tenant_id"] = path_parts[idx + 1]

        return actor

    def _determine_event_type(
        self, method: str, path: str, status_code: int
    ) -> EventType:
        """Determine the appropriate event type based on request details."""
        # Auth-related endpoints
        if "/auth/" in path or "/login" in path or "/oauth" in path:
            if status_code < 400:
                return EventType.LOGIN_SUCCESS
            return EventType.LOGIN_FAILURE

        if "/logout" in path:
            return EventType.LOGOUT

        # API key endpoints
        if "/api-keys" in path or "/apikeys" in path:
            if method == "POST":
                return EventType.API_KEY_CREATED
            if method == "DELETE":
                return EventType.API_KEY_REVOKED
            return EventType.API_KEY_USED

        # Webhook endpoints
        if "/webhooks" in path or "/webhook" in path:
            return EventType.WEBHOOK_RECEIVED

        # Incident endpoints
        if "/incidents" in path:
            if method == "GET":
                return EventType.INCIDENT_VIEWED
            if method == "POST":
                return EventType.INCIDENT_CREATED
            if method == "PUT" or method == "PATCH":
                return EventType.INCIDENT_UPDATED

        # Settings endpoints
        if "/settings" in path or "/config" in path:
            if method == "GET":
                return EventType.SETTINGS_VIEWED
            return EventType.SETTINGS_UPDATED

        # User management
        if "/users" in path or "/members" in path or "/team" in path:
            if method == "POST":
                return EventType.USER_CREATED
            if method == "DELETE":
                return EventType.USER_DELETED
            if method == "PUT" or method == "PATCH":
                return EventType.USER_UPDATED

        # Audit log access
        if "/audit" in path:
            if "/export" in path:
                return EventType.AUDIT_LOG_EXPORTED
            return EventType.AUDIT_LOG_VIEWED

        # Default based on access
        if status_code == 403:
            return EventType.ACCESS_DENIED
        if status_code >= 400:
            return EventType.SYSTEM_ERROR

        return EventType.ACCESS_GRANTED

    def _determine_category(self, event_type: EventType) -> EventCategory:
        """Determine the category based on event type."""
        auth_events = {
            EventType.LOGIN_SUCCESS,
            EventType.LOGIN_FAILURE,
            EventType.LOGOUT,
            EventType.SESSION_CREATED,
            EventType.SESSION_EXPIRED,
            EventType.TOKEN_REFRESH,
        }
        if event_type in auth_events:
            return EventCategory.AUTHENTICATION

        authz_events = {
            EventType.ACCESS_GRANTED,
            EventType.ACCESS_DENIED,
            EventType.PERMISSION_CHECK,
            EventType.ROLE_ASSIGNED,
        }
        if event_type in authz_events:
            return EventCategory.AUTHORIZATION

        api_key_events = {
            EventType.API_KEY_CREATED,
            EventType.API_KEY_REVOKED,
            EventType.API_KEY_USED,
        }
        if event_type in api_key_events:
            return EventCategory.API_KEY

        webhook_events = {
            EventType.WEBHOOK_RECEIVED,
            EventType.WEBHOOK_PROCESSED,
            EventType.WEBHOOK_FAILED,
        }
        if event_type in webhook_events:
            return EventCategory.WEBHOOK

        data_events = {
            EventType.INCIDENT_VIEWED,
            EventType.INCIDENT_CREATED,
            EventType.INCIDENT_UPDATED,
            EventType.LOGS_ACCESSED,
        }
        if event_type in data_events:
            return EventCategory.DATA_ACCESS

        config_events = {
            EventType.SETTINGS_VIEWED,
            EventType.SETTINGS_UPDATED,
            EventType.FEATURE_ENABLED,
        }
        if event_type in config_events:
            return EventCategory.CONFIGURATION

        user_events = {
            EventType.USER_CREATED,
            EventType.USER_UPDATED,
            EventType.USER_DELETED,
        }
        if event_type in user_events:
            return EventCategory.USER_MANAGEMENT

        return EventCategory.SYSTEM

    def _determine_outcome(self, status_code: int) -> Outcome:
        """Determine outcome based on HTTP status code."""
        if status_code < 400:
            return Outcome.SUCCESS
        if status_code == 401 or status_code == 403:
            return Outcome.DENIED
        if status_code < 500:
            return Outcome.FAILURE
        return Outcome.ERROR

    async def _log_request(
        self,
        request: Request,
        response: Response,
        request_id: str,
        ip_address: str | None,
        user_agent: str | None,
        duration_ms: float,
    ) -> None:
        """Log an API request to the audit trail."""
        # Skip logging successful health checks even if not fully excluded
        if response.status_code == 200 and not self.log_all_requests:
            # Only log non-GET requests or error responses unless log_all is enabled
            if request.method == "GET" and response.status_code < 400:
                # Check if this is a "read-only" path we should still log
                path = request.url.path.lower()
                important_reads = ["/audit", "/users", "/settings", "/incidents"]
                if not any(imp in path for imp in important_reads):
                    return

        actor = self._extract_actor(request)
        method = request.method
        path = request.url.path
        status_code = response.status_code

        event_type = self._determine_event_type(method, path, status_code)
        category = self._determine_category(event_type)
        outcome = self._determine_outcome(status_code)

        action = f"{method} {path}"

        await audit_logger.log_event(
            category=category,
            event_type=event_type,
            action=action,
            tenant_id=actor["tenant_id"],
            user_id=actor["user_id"],
            user_email=actor["user_email"],
            api_key_id=actor["api_key_id"],
            session_id=actor["session_id"],
            outcome=outcome,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            request_path=path,
            request_method=method,
            metadata={
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "query_params": (
                    dict(request.query_params) if request.query_params else None
                ),
            },
        )

    async def _log_error(
        self,
        request: Request,
        error: Exception,
        request_id: str,
        ip_address: str | None,
        user_agent: str | None,
        duration_ms: float,
    ) -> None:
        """Log an error that occurred during request processing."""
        actor = self._extract_actor(request)
        method = request.method
        path = request.url.path

        await audit_logger.log_event(
            category=EventCategory.SYSTEM,
            event_type=EventType.SYSTEM_ERROR,
            action=f"{method} {path} (error)",
            tenant_id=actor["tenant_id"],
            user_id=actor["user_id"],
            user_email=actor["user_email"],
            api_key_id=actor["api_key_id"],
            session_id=actor["session_id"],
            outcome=Outcome.ERROR,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            request_path=path,
            request_method=method,
            metadata={
                "error_type": type(error).__name__,
                "error_message": str(error),
                "duration_ms": round(duration_ms, 2),
            },
        )


def add_audit_middleware(app: ASGIApp) -> ASGIApp:
    """Add audit middleware to a FastAPI application.

    Usage:
        from fastapi import FastAPI
        from src.audit.middleware import add_audit_middleware

        app = FastAPI()
        app.add_middleware(AuditMiddleware)
        # or
        app = add_audit_middleware(app)
    """
    settings = get_settings()
    if not settings.audit_enabled:
        return app

    return AuditMiddleware(app)


# Decorator for explicit audit logging on specific endpoints
def audit_log(
    event_type: EventType,
    category: EventCategory | None = None,
    action_template: str | None = None,
) -> Callable:
    """Decorator to explicitly log an audit event for an endpoint.

    Usage:
        @router.post("/api-keys")
        @audit_log(EventType.API_KEY_CREATED, action_template="Created API key: {name}")
        async def create_api_key(name: str, current_user: User = Depends(get_current_user)):
            ...
    """

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            # Get request from kwargs if available
            request: Request | None = kwargs.get("request")

            # Execute the endpoint
            result = await func(*args, **kwargs)

            # Build action string
            if action_template:
                action = action_template.format(**kwargs)
            else:
                action = f"{event_type.value}"

            # Extract actor info
            actor: dict[str, Any] = {}
            if request:
                if hasattr(request.state, "user"):
                    user = request.state.user
                    actor["tenant_id"] = getattr(user, "tenant_id", None)
                    actor["user_id"] = getattr(user, "id", None)
                    actor["user_email"] = getattr(user, "email", None)

            # Log the event
            await audit_logger.log_event(
                category=category or EventCategory.SYSTEM,
                event_type=event_type,
                action=action,
                **actor,
            )

            return result

        return wrapper

    return decorator
