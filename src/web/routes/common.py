"""Shared web route primitives, auth helpers, and template utilities."""

from datetime import datetime
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.templating import Jinja2Templates

from ...auth.middleware import AuthContext
from ...models import Severity

logger = structlog.get_logger()

# Set up templates
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Landing page router (root path)
landing_router = APIRouter(tags=["landing"])


async def require_dashboard_auth(request: Request) -> dict[str, str]:
    """Require a valid Supabase bearer token for dashboard routes.

    In production, this enforces Supabase authentication.

    In tests (and local dev setups) where Supabase Auth is disabled via
    `SUPABASE_AUTH_ENABLED=false`, we allow dashboard access with a
    deterministic "default" tenant and synthetic user id.

    Uses Authorization header or ic_access_token cookie.
    Browser requests (Accept: text/html) are redirected to /login instead
    of receiving a raw JSON 401.
    """

    from ...supabase_client import is_supabase_auth_enabled

    if not is_supabase_auth_enabled():
        return {"tenant_id": "default", "user_id": "test-user"}

    tenant_id, user_id = await _get_tenant_id_from_request(request)
    if not tenant_id or not user_id:
        # Browser navigation -> redirect to login for a friendly experience.
        # API calls still get a clean JSON 401.
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            raise DashboardAuthRedirect()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return {"tenant_id": tenant_id, "user_id": user_id}


class DashboardAuthRedirect(Exception):
    """Raised to redirect unauthenticated browser requests to /login."""

    pass


# Dashboard router
router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_dashboard_auth)],
)


def _map_status(raw_status: str | None) -> str:
    """Normalize processing statuses to lifecycle statuses."""
    status_map = {
        "processing": "triggered",
        "completed": "resolved",
        "error": "triggered",
    }
    normalized = str(raw_status or "processing").strip().lower()
    return status_map.get(normalized, normalized)


def mask_secret(value: str) -> str:
    """Mask a secret, showing only first/last 4 chars if long enough."""
    if not value:
        return "(not configured)"
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def format_datetime(dt: datetime | None) -> str:
    """Format datetime for display."""
    if not dt:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def format_datetime_short(dt: datetime | None) -> str:
    """Format datetime as compact but complete."""
    if not dt:
        return ""
    return dt.strftime("%b %d, %H:%M:%S UTC")


def severity_color(severity: Severity) -> str:
    """Get Tailwind color class for severity."""
    colors = {
        Severity.CRITICAL: "bg-red-600",
        Severity.HIGH: "bg-orange-500",
        Severity.MEDIUM: "bg-yellow-500",
        Severity.LOW: "bg-amber-500",
        Severity.INFO: "bg-gray-500",
    }
    return colors.get(severity, "bg-gray-500")


def status_color(status: str) -> str:
    """Get Tailwind color class for status."""
    colors = {
        "triggered": "bg-yellow-500",
        "acknowledged": "bg-blue-500",
        "resolved": "bg-green-500",
        "error": "bg-red-500",
        # Backward compatibility for legacy processing statuses.
        "processing": "bg-yellow-500",
        "completed": "bg-green-500",
    }
    normalized = str(status or "").strip().lower()
    return colors.get(normalized, "bg-gray-500")


def tenant_slug_from_auth(auth: AuthContext) -> str:
    """Resolve a tenant slug for service catalog operations."""
    if auth.tenant and auth.tenant.slug:
        return auth.tenant.slug
    return auth.tenant_id or "default"


# Add template filters
templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["format_datetime_short"] = format_datetime_short
templates.env.filters["severity_color"] = severity_color
templates.env.filters["status_color"] = status_color
templates.env.filters["mask_secret"] = mask_secret


async def _get_tenant_id_from_request(request: Request) -> tuple[str | None, str | None]:
    """Resolve (tenant_id, user_id) from a Supabase Bearer token.

    Returns (None, None) if no auth is provided.
    """

    token: str | None = None

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")

    # Browser navigation requests typically won't include Authorization headers.
    if not token:
        token = request.cookies.get("ic_access_token")

    if not token:
        return None, None

    from ...supabase_client import get_supabase_admin_client, is_supabase_db_enabled

    admin = get_supabase_admin_client()
    if not admin:
        return None, None

    # Validate token and get Supabase auth user
    try:
        user_response = admin.auth.get_user(token)
    except Exception:
        return None, None
    if not user_response or not user_response.user:
        return None, None

    user = user_response.user
    user_id = str(user.id)

    if not is_supabase_db_enabled():
        return "default", user_id

    email = (user.email or "").lower()
    if not email:
        return None, user_id

    from ...db.supabase_db import get_db

    db = get_db(use_admin=True)
    app_user = await db.get_user_by_email(email)

    # Defensive: if user is missing (e.g., legacy account), create tenant+user.
    if not app_user:
        slug = user_id
        tenant_name = email.split("@")[1] if "@" in email else email
        tenant = await db.ensure_tenant(slug=slug, name=tenant_name)
        app_user = await db.create_user(
            email=email,
            tenant_id=tenant["id"],
            name=(user.user_metadata or {}).get("full_name")
            or (user.user_metadata or {}).get("name"),
            role="owner",
        )

    return app_user.get("tenant_id"), user_id


__all__ = [
    "logger",
    "templates",
    "landing_router",
    "router",
    "require_dashboard_auth",
    "DashboardAuthRedirect",
    "_map_status",
    "status_color",
    "tenant_slug_from_auth",
    "_get_tenant_id_from_request",
]
