"""Authentication middleware and dependencies for FastAPI."""

from functools import wraps
from typing import Callable, Optional

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import (APIKeyHeader, HTTPAuthorizationCredentials,
                              HTTPBearer)

from .models import Session, Tenant, User, UserRole
from .service import auth_service

logger = structlog.get_logger()

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class AuthContext:
    """Authentication context available in requests."""

    def __init__(
        self,
        user: Optional[User] = None,
        tenant: Optional[Tenant] = None,
        session: Optional[Session] = None,
        api_key_id: Optional[str] = None,
    ):
        self.user = user
        self.tenant = tenant
        self.session = session
        self.api_key_id = api_key_id

    @property
    def is_authenticated(self) -> bool:
        return self.tenant is not None

    @property
    def tenant_id(self) -> Optional[str]:
        return self.tenant.id if self.tenant else None

    @property
    def user_id(self) -> Optional[str]:
        return self.user.id if self.user else None


async def get_auth_context(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    api_key: Optional[str] = Depends(api_key_header),
) -> AuthContext:
    """
    Extract authentication context from request.
    Supports both Bearer tokens (user sessions) and API keys.
    """
    # Try Bearer token first
    if bearer and bearer.credentials:
        session = await auth_service.get_session_by_token(bearer.credentials)
        if session:
            user = await auth_service.get_user(session.user_id)
            tenant = await auth_service.get_tenant(session.tenant_id)
            if user and tenant:
                return AuthContext(
                    user=user,
                    tenant=tenant,
                    session=session,
                )

    # Try API key
    if api_key:
        result = await auth_service.verify_api_key(api_key)
        if result:
            key, tenant = result
            return AuthContext(
                tenant=tenant,
                api_key_id=key.id,
            )

    # Not authenticated
    return AuthContext()


async def get_current_user(
    auth: AuthContext = Depends(get_auth_context),
) -> User:
    """Dependency that requires an authenticated user (not just API key)."""
    if not auth.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth.user


async def get_current_tenant(
    auth: AuthContext = Depends(get_auth_context),
) -> Tenant:
    """Dependency that requires authentication (user or API key)."""
    if not auth.tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth.tenant


def require_auth(func: Callable = None, *, require_user: bool = False):
    """
    Decorator to require authentication on a route.

    Args:
        require_user: If True, requires user auth (not just API key)
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request")
            auth = kwargs.get("auth")

            if not auth or not auth.is_authenticated:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            if require_user and not auth.user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User authentication required",
                )

            return await func(*args, **kwargs)

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


def require_role(*roles: UserRole):
    """Decorator to require specific user roles."""

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            auth: AuthContext = kwargs.get("auth")

            if not auth or not auth.user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            if auth.user.role not in roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Requires one of roles: {[r.value for r in roles]}",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


class AuthMiddleware:
    """
    ASGI middleware for authentication.
    Adds auth context to request state for use in templates.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Extract auth header
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            api_key_header = headers.get(b"x-api-key", b"").decode()

            auth_context = AuthContext()

            # Try Bearer token
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                session = await auth_service.get_session_by_token(token)
                if session:
                    user = await auth_service.get_user(session.user_id)
                    tenant = await auth_service.get_tenant(session.tenant_id)
                    if user and tenant:
                        auth_context = AuthContext(
                            user=user,
                            tenant=tenant,
                            session=session,
                        )

            # Try API key
            elif api_key_header:
                result = await auth_service.verify_api_key(api_key_header)
                if result:
                    key, tenant = result
                    auth_context = AuthContext(
                        tenant=tenant,
                        api_key_id=key.id,
                    )

            # Store in scope for access in request.state
            scope["auth"] = auth_context

        await self.app(scope, receive, send)
