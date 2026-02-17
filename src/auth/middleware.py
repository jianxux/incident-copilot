"""Authentication middleware and dependencies for FastAPI."""

from collections.abc import Callable
from functools import wraps

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

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
        user: User | None = None,
        tenant: Tenant | None = None,
        session: Session | None = None,
        api_key_id: str | None = None,
    ):
        self.user = user
        self.tenant = tenant
        self.session = session
        self.api_key_id = api_key_id

    @property
    def is_authenticated(self) -> bool:
        return self.tenant is not None

    @property
    def tenant_id(self) -> str | None:
        return self.tenant.id if self.tenant else None

    @property
    def user_id(self) -> str | None:
        return self.user.id if self.user else None


async def get_auth_context(
    request: Request,
    bearer: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    api_key: str | None = Depends(api_key_header),
) -> AuthContext:
    """
    Extract authentication context from request.
    Supports both Bearer tokens (user sessions) and API keys.
    """
    # Try Bearer token first
    if bearer and bearer.credentials:
        # Legacy internal sessions
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

        # Supabase JWT fallback — validate token and build context from DB
        ctx = await _try_supabase_auth(bearer.credentials)
        if ctx:
            return ctx

    # Also try cookie (for server-rendered pages)
    if not bearer or not bearer.credentials:
        cookie_token = request.cookies.get("ic_access_token")
        if cookie_token:
            ctx = await _try_supabase_auth(cookie_token)
            if ctx:
                return ctx

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


async def _try_supabase_auth(token: str) -> AuthContext | None:
    """Validate a Supabase JWT and return an AuthContext if valid."""
    try:
        from ..supabase_client import get_supabase_admin_client, is_supabase_db_enabled

        admin = get_supabase_admin_client()
        if not admin:
            return None

        user_response = admin.auth.get_user(token)
        if not user_response or not user_response.user:
            return None

        su = user_response.user
        email = (su.email or "").lower()
        if not email:
            return None

        if not is_supabase_db_enabled():
            # Minimal context without DB
            return AuthContext(
                user=User(id=str(su.id), email=email, name=email, tenant_id="default", role=UserRole.OWNER),
                tenant=Tenant(id="default", name="default", slug="default"),
            )

        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        app_user = await db.get_user_by_email(email)

        if not app_user:
            # Auto-create tenant + user for first-time Supabase auth users
            slug = str(su.id)
            tenant_name = email.split("@")[1] if "@" in email else email
            tenant_data = await db.ensure_tenant(slug=slug, name=tenant_name)
            app_user = await db.create_user(
                email=email,
                tenant_id=tenant_data["id"],
                name=(su.user_metadata or {}).get("full_name")
                or (su.user_metadata or {}).get("name"),
                role="owner",
            )

        tenant_data = await db.get_tenant(app_user["tenant_id"])
        if not tenant_data:
            return None

        return AuthContext(
            user=User(
                id=app_user["id"],
                email=app_user.get("email", email),
                name=app_user.get("name") or email,
                tenant_id=app_user["tenant_id"],
                role=UserRole(app_user.get("role", "owner")),
            ),
            tenant=Tenant(
                id=tenant_data["id"],
                name=tenant_data.get("name", ""),
                slug=tenant_data.get("slug", ""),
            ),
        )
    except Exception as e:
        logger.debug("supabase_auth_fallback_failed", error=str(e))
        return None


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
