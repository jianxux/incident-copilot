"""Web routes for the Incident Copilot dashboard.

TODO: This file is a monolith and should be refactored into focused route modules.
"""

import asyncio
import json
import random
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from ..auth.middleware import AuthContext, get_auth_context
from ..config import get_settings
from ..models import (
    AILogSummary,
    ContextCard,
    DatadogContext,
    Deployment,
    GitHubContext,
    LogSummary,
    MetricSnapshot,
    Severity,
)
from .store import incident_store

logger = structlog.get_logger()

# Background PagerDuty auto-sync: track last sync time per tenant (epoch seconds)
_pd_sync_timestamps: dict[str, float] = {}
_PD_SYNC_INTERVAL = 300  # seconds (5 minutes)

# Set up templates
templates_dir = Path(__file__).parent / "templates"
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

    from ..supabase_client import is_supabase_auth_enabled

    if not is_supabase_auth_enabled():
        return {"tenant_id": "default", "user_id": "test-user"}

    tenant_id, user_id = await _get_tenant_id_from_request(request)
    if not tenant_id or not user_id:
        # Browser navigation → redirect to login for a friendly experience.
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
        "processing": "bg-yellow-500",
        "completed": "bg-green-500",
        "error": "bg-red-500",
    }
    return colors.get(status, "bg-gray-500")


def tenant_slug_from_auth(auth: AuthContext) -> str:
    """Resolve a tenant slug for service catalog operations."""
    if auth.tenant and auth.tenant.slug:
        return auth.tenant.slug
    return auth.tenant_id or "default"


# Add template filters
templates.env.filters["format_datetime"] = format_datetime
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

    from ..supabase_client import get_supabase_admin_client, is_supabase_db_enabled

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

    from ..db.supabase_db import get_db

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


# ============================================================================
# Landing Page Routes
# ============================================================================


@landing_router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Marketing landing page for Incident Copilot."""
    return templates.TemplateResponse(
        "landing.html",
        {"request": request},
    )


@landing_router.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "incident-copilot"}


async def _background_pd_sync(tenant_id: str) -> None:
    """Fire-and-forget background sync of PagerDuty incidents for a tenant."""
    try:
        # 1. Resolve PD token (oauth_token_store then integration_configs)
        oauth_token = ""
        api_key = ""

        try:
            from ..integrations.oauth_tokens import oauth_token_store

            token_rec = await oauth_token_store.get_token(tenant_id, "pagerduty")
            if token_rec and token_rec.access_token:
                oauth_token = token_rec.access_token
        except Exception:
            pass

        if not oauth_token:
            try:
                from ..db.supabase_db import get_db
                from ..security.crypto import decrypt_json

                db = get_db(use_admin=True)
                rows = db.client.table("integration_configs").select("config").eq(
                    "tenant_id", tenant_id
                ).eq("type", "pagerduty").eq("is_active", True).limit(1).execute()

                if rows.data:
                    config = rows.data[0].get("config", {})
                    encrypted = config.get("encrypted", "") if isinstance(config, dict) else ""
                    if encrypted:
                        decrypted = decrypt_json(encrypted)
                        oauth = decrypted.get("oauth", {})
                        oauth_token = oauth.get("access_token", "")
                        api_key = decrypted.get("api_key", "")
            except Exception:
                pass

        token = oauth_token or api_key
        if not token:
            return  # No PD connection — silently skip

        pd_auth = f"Bearer {oauth_token}" if oauth_token else f"Token token={api_key}"

        # 2. Fetch last 25 incidents from PagerDuty
        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.pagerduty.com/incidents",
                headers={
                    "Authorization": pd_auth,
                    "Content-Type": "application/json",
                    "Accept": "application/vnd.pagerduty+json;version=2",
                },
                params={
                    "statuses[]": ["triggered", "acknowledged", "resolved"],
                    "sort_by": "created_at:desc",
                    "limit": 25,
                },
            )
            if resp.status_code != 200:
                logger.warning("bg_pd_sync_api_error", status=resp.status_code, tenant_id=tenant_id)
                return

            pd_incidents = resp.json().get("incidents", [])

        # 3. Upsert each incident
        for inc in pd_incidents:
            inc_id = inc.get("id", "")
            if not inc_id:
                continue

            urgency = inc.get("urgency", "low")
            severity = Severity.HIGH if urgency == "high" else Severity.LOW

            service_summary = ""
            svc = inc.get("service")
            if isinstance(svc, dict):
                service_summary = svc.get("summary", "")

            created_at_str = inc.get("created_at", "")
            try:
                triggered_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                triggered_at = datetime.now(UTC)

            assigned_to = []
            for assignment in inc.get("assignments", []):
                assignee = assignment.get("assignee", {})
                if isinstance(assignee, dict) and assignee.get("summary"):
                    assigned_to.append(assignee["summary"])

            ep = inc.get("escalation_policy", {})
            ep_summary = ep.get("summary", "") if isinstance(ep, dict) else ""

            metadata = {
                "provider": "pagerduty",
                "status": inc.get("status", ""),
                "urgency": urgency,
                "assigned_to": assigned_to,
                "escalation_policy": ep_summary,
            }

            await incident_store.add_incident(
                incident_id=inc_id,
                title=inc.get("title", ""),
                service_name=service_summary,
                severity=severity,
                triggered_at=triggered_at,
                source="pagerduty",
                source_url=inc.get("html_url", ""),
                source_id=str(inc.get("incident_number", "")),
                metadata=metadata,
                tenant_id=tenant_id,
            )

            if inc.get("status") == "resolved":
                await incident_store.complete_incident(
                    inc_id,
                    ContextCard(
                        incident_id=inc_id,
                        title=inc.get("title", ""),
                        severity=severity,
                        service_name=service_summary,
                        triggered_at=triggered_at,
                        assembled_at=datetime.now(UTC),
                        assembly_time_ms=0,
                    ),
                    metadata={"resolved_via_sync": True},
                    tenant_id=tenant_id,
                )

        # 4. Update timestamp on success
        import time

        _pd_sync_timestamps[tenant_id] = time.time()
        logger.info("bg_pd_sync_complete", tenant_id=tenant_id, synced=len(pd_incidents))

    except Exception as exc:
        logger.warning(
            "bg_pd_sync_failed",
            tenant_id=tenant_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )


async def _maybe_trigger_pd_sync(tenant_id: str) -> bool:
    """Sync PD incidents if stale. Returns True if sync was awaited (first time)."""
    import time

    now = time.time()
    last = _pd_sync_timestamps.get(tenant_id, 0)
    if now - last < _PD_SYNC_INTERVAL:
        return False

    first_sync = last == 0  # Never synced before for this tenant
    # Mark immediately to prevent duplicate launches
    _pd_sync_timestamps[tenant_id] = now

    if first_sync:
        # First sync: await it so the response includes PD incidents
        await _background_pd_sync(tenant_id)
        return True
    else:
        # Subsequent syncs: fire-and-forget
        asyncio.create_task(_background_pd_sync(tenant_id))
        return False


@landing_router.get("/api/incidents")
async def api_incidents(
    request: Request,
    auth_data: dict[str, str] = Depends(require_dashboard_auth),
):
    """Tenant-scoped JSON API endpoint for incidents list."""
    tenant_id = auth_data["tenant_id"]

    # Sync PagerDuty incidents — first load awaits, subsequent are background
    await _maybe_trigger_pd_sync(tenant_id)

    def _map_status(raw_status: str | None) -> str:
        status_map = {
            "processing": "triggered",
            "completed": "resolved",
            "error": "triggered",
        }
        normalized = str(raw_status or "processing").strip().lower()
        return status_map.get(normalized, normalized)

    # When Supabase DB is disabled, fall back to in-memory store.
    from ..supabase_client import is_supabase_db_enabled

    if not is_supabase_db_enabled():
        incidents = await incident_store.get_all_incidents()
        serialized = []
        for i in incidents:
            triggered_at = i.triggered_at.isoformat()
            processed_at = i.processed_at.isoformat() if i.processed_at else None
            created_at = triggered_at
            updated_at = processed_at or triggered_at
            status = _map_status(i.status)

            serialized.append(
                {
                    "id": i.incident_id,
                    "incident_id": i.incident_id,
                    "title": i.title,
                    "service": i.service_name,
                    "service_name": i.service_name,
                    "severity": i.severity.value,
                    "status": status,
                    "source": i.source or "",
                    "source_url": i.source_url or "",
                    "source_id": i.source_id or "",
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "triggered_at": triggered_at,
                    "processed_at": processed_at,
                }
            )

        return {"incidents": serialized, "total": len(serialized)}

    from ..db.supabase_db import get_db

    db = get_db(use_admin=True)
    rows = await db.list_processing_incidents(tenant_id=tenant_id, limit=100, offset=0)

    def _format_incident(r: dict) -> dict:
        triggered = r.get("triggered_at")
        processed = r.get("processed_at")
        created_at = r.get("created_at") or triggered
        updated_at = r.get("updated_at") or processed or created_at
        duration_seconds = None
        if triggered and processed:
            try:
                from datetime import datetime, timezone
                t0 = datetime.fromisoformat(str(triggered).replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(str(processed).replace("Z", "+00:00"))
                duration_seconds = int((t1 - t0).total_seconds())
            except Exception as e:
                logger.warning(
                    "incident_duration_parse_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    incident_id=r.get("id"),
                )

        # Extract verdict summary from metadata if available
        meta = r.get("metadata") or {}
        verdict_summary = None
        if isinstance(meta, dict):
            verdict = meta.get("verdict") or meta.get("ai_verdict") or {}
            if isinstance(verdict, dict):
                verdict_summary = verdict.get("summary") or verdict.get("one_liner")
            elif isinstance(verdict, str):
                verdict_summary = verdict[:200]

        return {
            "id": r["id"],
            "incident_id": r["id"],
            "title": r.get("title") or "",
            "description": r.get("description") or "",
            "service": r.get("service") or "",
            "service_name": r.get("service") or "",  # backward compat
            "severity": r.get("severity") or "medium",
            "status": _map_status(r.get("status")),
            "source": r.get("source") or "",
            "source_url": r.get("source_url") or "",
            "source_id": r.get("source_id") or "",
            "triggered_at": triggered,
            "processed_at": processed,
            "created_at": created_at,
            "updated_at": updated_at,
            "duration_seconds": duration_seconds,
            "verdict_summary": verdict_summary,
            "error_message": r.get("error_message"),
        }

    return {
        "incidents": [_format_incident(r) for r in rows],
        "total": len(rows),
    }


@landing_router.get("/api/incidents/stats")
async def api_incident_stats(
    request: Request,
    auth_data: dict[str, str] = Depends(require_dashboard_auth),
):
    """Return incident statistics: total, open, resolved today, avg MTTR."""
    tenant_id = auth_data["tenant_id"]

    from ..supabase_client import is_supabase_db_enabled

    if not is_supabase_db_enabled():
        incidents = await incident_store.get_all_incidents()
    else:
        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        rows = await db.list_processing_incidents(
            tenant_id=tenant_id, limit=500, offset=0
        )
        incidents = [
            type(
                "Inc",
                (),
                {
                    "status": r.get("status") or "processing",
                    "processed_at": (
                        datetime.fromisoformat(
                            str(r["processed_at"]).replace("Z", "+00:00")
                        )
                        if r.get("processed_at")
                        else None
                    ),
                    "triggered_at": (
                        datetime.fromisoformat(
                            str(r["triggered_at"]).replace("Z", "+00:00")
                        )
                        if r.get("triggered_at")
                        else None
                    ),
                },
            )()
            for r in rows
        ]

    total = len(incidents)
    open_count = sum(
        1 for i in incidents if getattr(i, "status", "processing") != "completed"
    )

    today = datetime.now(UTC).date()
    resolved_today = 0
    mttr_values: list[float] = []

    for i in incidents:
        p = getattr(i, "processed_at", None)
        t = getattr(i, "triggered_at", None)
        st = getattr(i, "status", "processing")
        if st == "completed" and p:
            if hasattr(p, "date") and p.date() == today:
                resolved_today += 1
            if t and p:
                mttr_values.append((p - t).total_seconds() / 60.0)

    avg_mttr_minutes = round(sum(mttr_values) / len(mttr_values), 1) if mttr_values else None

    return {
        "total": total,
        "open": open_count,
        "resolved_today": resolved_today,
        "avg_mttr_minutes": avg_mttr_minutes,
    }


@landing_router.get("/api/incidents/{incident_id}/context")
async def api_incident_context(
    incident_id: str,
    auth_data: dict[str, str] = Depends(require_dashboard_auth),
):
    """Return the context card JSON for a specific incident."""
    incident = await incident_store.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if not incident.context_card:
        return {}
    return incident.context_card.model_dump(mode="json")


@landing_router.get("/api/incidents/{incident_id}")
async def api_incident_detail(
    incident_id: str,
    auth_data: dict[str, str] = Depends(require_dashboard_auth),
):
    """Return a single incident by ID."""
    incident = await incident_store.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {
        "id": incident.incident_id,
        "title": incident.title,
        "service": incident.service_name,
        "severity": incident.severity.value,
        "status": incident.status,
        "created_at": incident.triggered_at.isoformat(),
        "updated_at": (
            incident.processed_at.isoformat()
            if incident.processed_at
            else incident.triggered_at.isoformat()
        ),
        "source": incident.source,
        "source_url": incident.source_url,
    }


@landing_router.get("/api/dashboard/stats")
async def api_dashboard_stats(
    request: Request,
    auth_data: dict[str, str] = Depends(require_dashboard_auth),
):
    """Tenant-scoped JSON API endpoint for dashboard stats."""
    tenant_id = auth_data["tenant_id"]

    from ..supabase_client import is_supabase_db_enabled

    if not is_supabase_db_enabled():
        return await incident_store.get_stats()

    # Compute stats from incidents list
    from ..models import Severity
    from ..db.supabase_db import get_db

    db = get_db(use_admin=True)
    rows = await db.list_processing_incidents(tenant_id=tenant_id, limit=100, offset=0)

    by_status: dict[str, int] = {"processing": 0, "completed": 0, "error": 0}
    by_severity: dict[str, int] = {s.value: 0 for s in Severity}

    for r in rows:
        st = r.get("status") or "processing"
        by_status[st] = by_status.get(st, 0) + 1
        sev = r.get("severity") or Severity.MEDIUM.value
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {"total": len(rows), "by_status": by_status, "by_severity": by_severity}


# ============================================================================
# Auth Callback (Supabase PKCE flow)
# ============================================================================


@landing_router.get("/auth/callback", response_class=HTMLResponse)
async def auth_callback(request: Request):
    """Handle Supabase Auth PKCE callback.

    Supabase redirects here with ?code=xxx after OAuth.
    The code exchange must happen client-side where the PKCE code verifier
    is stored (in the browser's storage from the initial OAuth request).
    """
    return HTMLResponse(
        content="""
<!DOCTYPE html>
<html>
<head>
    <title>Authenticating...</title>
    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
</head>
<body style="display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:sans-serif;background:#f8fafc;">
    <div style="text-align:center;">
        <div style="width:40px;height:40px;border:3px solid #e2e8f0;border-top-color:#3b82f6;border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 16px;"></div>
        <p style="color:#64748b;">Completing sign in...</p>
    </div>
    <style>@keyframes spin { from { transform:rotate(0deg); } to { transform:rotate(360deg); } }</style>
    <script>
        const hash = window.location.hash.substring(1);
        const hashParams = new URLSearchParams(hash);
        const queryParams = new URLSearchParams(window.location.search);
        const flow = queryParams.get('flow') || 'login';

        const accessToken = hashParams.get('access_token');
        const refreshToken = hashParams.get('refresh_token');
        const code = queryParams.get('code');

        function handleAuthComplete(token, refresh, userData) {
            localStorage.setItem('access_token', token);
            localStorage.setItem('refresh_token', refresh || '');
            if (userData) localStorage.setItem('user', JSON.stringify(userData));

            // Also set a cookie so server-rendered dashboard routes can enforce auth.
            // Note: this cookie is NOT HttpOnly because it is set client-side.
            // It mirrors the token already stored in localStorage.
            const secure = window.location.protocol === 'https:' ? '; Secure' : '';
            document.cookie = `ic_access_token=${encodeURIComponent(token)}; Path=/; SameSite=Lax${secure}`;

            // Check if user has a profile (has signed up before)
            fetch('/api/auth/supabase/check-profile', {
                headers: { 'Authorization': 'Bearer ' + token }
            })
            .then(r => r.json())
            .then(data => {
                if (data && data.tenant_id) {
                    localStorage.setItem('tenant_id', data.tenant_id);
                }

                if (flow === 'login' && !data.has_profile) {
                    // User hasn't signed up yet — reject login
                    localStorage.removeItem('access_token');
                    localStorage.removeItem('refresh_token');
                    localStorage.removeItem('user');
                    localStorage.removeItem('tenant_id');
                    window.location.href = '/login?error=no_account';
                } else if (flow === 'signup' && !data.has_profile) {
                    // New signup — send to onboarding
                    window.location.href = '/dashboard/onboarding-wizard';
                } else {
                    // Existing user — go to dashboard
                    window.location.href = '/dashboard';
                }
            })
            .catch(() => {
                // If check fails, allow through (graceful degradation)
                window.location.href = '/dashboard';
            });
        }

        if (accessToken && refreshToken) {
            // Implicit flow
            fetch('/api/auth/supabase/user', {
                headers: { 'Authorization': 'Bearer ' + accessToken }
            })
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                handleAuthComplete(accessToken, refreshToken, data ? data.user : null);
            })
            .catch(() => {
                handleAuthComplete(accessToken, refreshToken, null);
            });
        } else if (code) {
            // PKCE flow
            fetch('/api/auth/supabase/exchange?code=' + encodeURIComponent(code))
            .then(r => r.json())
            .then(data => {
                if (data.access_token) {
                    handleAuthComplete(data.access_token, data.refresh_token, data.user);
                } else {
                    window.location.href = '/login?error=oauth_token_failed';
                }
            })
            .catch(() => {
                window.location.href = '/login?error=oauth_token_failed';
            });
        } else {
            window.location.href = '/login?error=oauth_invalid';
        }
    </script>
</body>
</html>
"""
    )


# ============================================================================
# Auth Pages (login, signup, etc.)
# ============================================================================


@landing_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    """Login page."""
    from ..auth.oauth import get_available_providers
    from ..supabase_client import is_supabase_auth_enabled

    error_messages = {
        "no_account": "No account found. Please sign up first.",
        "session_expired": "Your session has expired. Please sign in again.",
        "oauth_denied": "You cancelled the login process.",
        "oauth_invalid": "Invalid OAuth response. Please try again.",
        "oauth_invalid_state": "Session expired. Please try again.",
        "oauth_not_configured": "This login method is not configured.",
        "oauth_token_failed": "Failed to authenticate. Please try again.",
        "oauth_user_failed": "Failed to get user info. Please try again.",
        "session_expired": "Your session has expired. Please sign in again.",
    }

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "providers": get_available_providers(),
            "supabase_auth_enabled": is_supabase_auth_enabled(),
            "error": error_messages.get(error, error) if error else None,
        },
    )


@landing_router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    """Signup page."""
    from ..auth.oauth import get_available_providers
    from ..supabase_client import is_supabase_auth_enabled

    return templates.TemplateResponse(
        "signup.html",
        {
            "request": request,
            "providers": get_available_providers(),
            "supabase_auth_enabled": is_supabase_auth_enabled(),
        },
    )


# ============================================================================
# Dashboard Routes
# ============================================================================


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Main dashboard page.

    Auth is handled client-side via Supabase tokens stored in localStorage.
    This page renders a shell and loads tenant-scoped data via authenticated
    API calls.
    """
    empty_stats = {
        "total": "—",
        "by_status": {"processing": "—", "completed": "—", "error": "—"},
        "by_severity": {
            "critical": "—",
            "high": "—",
            "medium": "—",
            "low": "—",
            "info": "—",
        },
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "incidents": [],
            "stats": empty_stats,
            "page_title": "Dashboard",
        },
    )


@router.get("/incidents", response_class=HTMLResponse)
async def incidents_list_page(request: Request):
    """Dedicated incidents list page with search, filters, and sorting."""
    return templates.TemplateResponse(
        "incidents.html",
        {
            "request": request,
            "page_title": "Incidents",
        },
    )


@router.get("/onboarding")
async def onboarding_page(request: Request):
    """Legacy onboarding — redirect to unified wizard."""
    return RedirectResponse(url="/dashboard/onboarding-wizard", status_code=302)


@router.get("/onboarding-wizard", response_class=HTMLResponse)
async def onboarding_wizard_page(request: Request):
    """Customer-friendly onboarding wizard."""
    settings = get_settings()
    webhook_url = f"{settings.app_url}/webhooks/pagerduty"

    return templates.TemplateResponse(
        "onboarding_wizard.html",
        {
            "request": request,
            "page_title": "Onboarding",
            "webhook_url": webhook_url,
        },
    )


@router.get("/onboarding-success", response_class=HTMLResponse)
async def onboarding_success_page(
    request: Request,
    incident_id: str | None = None,
):
    """Onboarding completion page after first successful test incident."""
    return templates.TemplateResponse(
        "onboarding_success.html",
        {
            "request": request,
            "page_title": "Onboarding Complete",
            "incident_id": incident_id,
        },
    )


@router.get("/services", response_class=HTMLResponse)
async def service_catalog_page(request: Request):
    """Service catalog dashboard page."""
    return templates.TemplateResponse(
        "services.html",
        {
            "request": request,
            "page_title": "Service Catalog",
        },
    )


@router.get("/billing", response_class=HTMLResponse)
async def billing_page(request: Request):
    """Billing and subscription management page."""
    return templates.TemplateResponse(
        "billing.html",
        {
            "request": request,
            "page_title": "Billing",
        },
    )


@router.get("/billing/success", response_class=HTMLResponse)
async def billing_success_page(request: Request):
    """Billing success page after checkout."""
    return templates.TemplateResponse(
        "billing.html",
        {
            "request": request,
            "page_title": "Billing",
            "success": True,
        },
    )


@router.get("/handoff", response_class=HTMLResponse)
async def handoff_page(request: Request):
    """On-call handoff dashboard page."""
    return templates.TemplateResponse(
        "handoff.html",
        {
            "request": request,
            "page_title": "Handoff",
        },
    )


@router.get("/incident/{incident_id}", response_class=HTMLResponse)
async def incident_detail(
    request: Request,
    incident_id: str,
    auth_data: dict[str, str] = Depends(require_dashboard_auth),
):
    """Incident detail page showing full context card."""
    tenant_id = auth_data.get("tenant_id")
    incident = await incident_store.get_incident(incident_id, tenant_id=tenant_id)

    if not incident:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": f"Incident {incident_id} not found",
                "page_title": "Not Found",
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        "incident_detail.html",
        {
            "request": request,
            "incident": incident,
            "card": incident.context_card,
            "page_title": f"Incident {incident_id[:8]}...",
        },
    )


@router.get("/incident/{incident_id}/chat", response_class=HTMLResponse)
async def incident_chat(
    request: Request,
    incident_id: str,
    auth_data: dict[str, str] = Depends(require_dashboard_auth),
):
    """Full-page AI Copilot chat for an incident."""
    tenant_id = auth_data.get("tenant_id")
    incident = await incident_store.get_incident(incident_id, tenant_id=tenant_id)

    if not incident:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": f"Incident {incident_id} not found",
                "page_title": "Not Found",
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        "copilot_chat.html",
        {
            "request": request,
            "incident": incident,
            "incident_id": incident_id,
            "page_title": f"Copilot Chat - {incident_id[:8]}...",
        },
    )


@router.get("/incident/{incident_id}/timeline", response_class=HTMLResponse)
async def incident_timeline(
    request: Request,
    incident_id: str,
    auth_data: dict[str, str] = Depends(require_dashboard_auth),
):
    """Interactive timeline view for an incident."""
    from .timeline import TimelineBuilder, TimelineEventType, format_duration

    tenant_id = auth_data.get("tenant_id")
    incident = await incident_store.get_incident(incident_id, tenant_id=tenant_id)

    if not incident:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": f"Incident {incident_id} not found",
                "page_title": "Not Found",
            },
            status_code=404,
        )

    # Build timeline from context card
    builder = TimelineBuilder()
    incident_data = {
        "notification_sent": True,
        "notification_channel": "Slack",
        "notification_time": incident.processed_at,
    }

    if incident.context_card:
        events = builder.build_from_context_card(incident.context_card, incident_data)
    else:
        events = []

    # Calculate duration
    start = incident.triggered_at
    end = incident.processed_at or datetime.now(UTC)
    duration = format_duration(start, end) if start else "Unknown"

    # Calculate stats
    stats = {
        "alerts": len([e for e in events if "alert" in e.event_type.value]),
        "deployments": len(
            [e for e in events if e.event_type == TimelineEventType.DEPLOYMENT]
        ),
        "errors": len(
            [e for e in events if e.event_type == TimelineEventType.LOG_ERROR]
        ),
        "key_events": len([e for e in events if e.is_key_event]),
    }

    return templates.TemplateResponse(
        "timeline.html",
        {
            "request": request,
            "incident_id": incident_id,
            "incident_title": incident.title,
            "events": events,
            "duration": duration,
            "stats": stats,
            "page_title": f"Timeline - {incident_id[:8]}...",
        },
    )


@router.get("/api/incidents/{incident_id}/timeline")
async def get_incident_timeline_api(incident_id: str):
    """API endpoint to get timeline data as JSON."""
    from .timeline import TimelineBuilder

    incident = await incident_store.get_incident(incident_id)

    if not incident:
        return {"error": "Incident not found"}, 404

    builder = TimelineBuilder()
    incident_data = {
        "notification_sent": True,
        "notification_channel": "Slack",
    }

    if incident.context_card:
        builder.build_from_context_card(incident.context_card, incident_data)

    return {
        "incident_id": incident_id,
        "events": builder.to_dict(),
    }


@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    """Configuration page showing API key status."""
    settings = get_settings()

    config_items = [
        {
            "name": "PagerDuty API Key",
            "value": settings.pagerduty_api_key,
            "env_var": "PAGERDUTY_API_KEY",
            "description": "Used to fetch incident details",
        },
        {
            "name": "PagerDuty Webhook Secret",
            "value": settings.pagerduty_webhook_secret,
            "env_var": "PAGERDUTY_WEBHOOK_SECRET",
            "description": "Validates webhook signatures",
        },
        {
            "name": "GitHub Token",
            "value": settings.github_token,
            "env_var": "GITHUB_TOKEN",
            "description": "Fetches recent deploys and commits",
        },
        {
            "name": "GitHub Organization",
            "value": settings.github_org,
            "env_var": "GITHUB_ORG",
            "description": "Organization for repo lookups",
            "show_full": True,
        },
        {
            "name": "Datadog API Key",
            "value": settings.datadog_api_key,
            "env_var": "DATADOG_API_KEY",
            "description": "Fetches logs and metrics",
        },
        {
            "name": "Datadog App Key",
            "value": settings.datadog_app_key,
            "env_var": "DATADOG_APP_KEY",
            "description": "Required for Datadog API access",
        },
        {
            "name": "Datadog Site",
            "value": settings.datadog_site,
            "env_var": "DATADOG_SITE",
            "description": "Datadog regional endpoint",
            "show_full": True,
        },
        {
            "name": "Slack Bot Token",
            "value": settings.slack_bot_token,
            "env_var": "SLACK_BOT_TOKEN",
            "description": "Posts context cards to Slack",
        },
        {
            "name": "Slack Default Channel",
            "value": settings.slack_default_channel,
            "env_var": "SLACK_DEFAULT_CHANNEL",
            "description": "Default channel for notifications",
            "show_full": True,
        },
        {
            "name": "Anthropic API Key",
            "value": settings.anthropic_api_key,
            "env_var": "ANTHROPIC_API_KEY",
            "description": "AI-powered log summarization",
        },
        {
            "name": "AI Model",
            "value": settings.ai_model,
            "env_var": "AI_MODEL",
            "description": "Claude model for analysis",
            "show_full": True,
        },
    ]

    return templates.TemplateResponse(
        "config.html",
        {
            "request": request,
            "config_items": config_items,
            "page_title": "Configuration",
        },
    )


@router.get("/events")
async def sse_events(request: Request):
    """Server-Sent Events endpoint for real-time updates."""

    async def event_generator():
        queue = await incident_store.subscribe()
        try:
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"

            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                try:
                    # Wait for events with timeout
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
        finally:
            await incident_store.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/incidents")
async def api_incidents_dashboard_scope(
    request: Request,
    auth_data: dict[str, str] = Depends(require_dashboard_auth),
):
    """Backward-compatible tenant-scoped incidents endpoint under /dashboard."""
    return await api_incidents(request, auth_data)


@router.patch("/api/incidents/{incident_id}/status")
async def update_incident_status(
    incident_id: str,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
):
    """Update incident status from dashboard."""
    tenant_id = auth.tenant_id or "default"
    body = await request.json()
    new_status = body.get("status", "").strip()

    status_aliases = {
        "triggered": "processing",
        "acknowledged": "processing",
        "resolved": "completed",
        "processing": "processing",
        "completed": "completed",
        "error": "error",
    }
    canonical_status = status_aliases.get(new_status)
    if canonical_status is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid status. Use: processing, completed, error",
        )

    try:
        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        update_data: dict = {"status": canonical_status}
        if canonical_status == "completed":
            from datetime import datetime, timezone
            update_data["processed_at"] = datetime.now(timezone.utc).isoformat()
        elif canonical_status == "processing":
            update_data["processed_at"] = None

        await db._to_thread(
            lambda: db.client.table("incidents").update(update_data).eq(
                "id", incident_id
            ).eq("tenant_id", tenant_id).execute()
        )
        return {"ok": True, "incident_id": incident_id, "status": canonical_status}
    except Exception as exc:
        logger.warning("update_incident_status_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/stats")
async def api_stats_dashboard_scope(
    request: Request,
    auth_data: dict[str, str] = Depends(require_dashboard_auth),
):
    """Backward-compatible tenant-scoped stats endpoint under /dashboard."""
    return await api_dashboard_stats(request, auth_data)


# =========================================================================
# Onboarding APIs
# =========================================================================


class DashboardServiceCreateRequest(BaseModel):
    """Create request for onboarding wizard service list."""

    name: str = Field(min_length=1, max_length=120)


@router.get("/api/services")
async def dashboard_list_services(
    auth: AuthContext = Depends(get_auth_context),
):
    """List services for onboarding wizard via dashboard-scoped API."""
    from ..services.store import get_service_catalog_store

    tenant_slug = tenant_slug_from_auth(auth)
    services = await get_service_catalog_store().list_services(tenant_slug=tenant_slug)
    return {
        "services": [
            {
                "id": service.id,
                "name": service.name,
                "description": service.description,
                "team": service.team,
                "source": (service.metadata or {}).get("source", "manual"),
                "metadata": service.metadata or {},
                "created_at": service.created_at.isoformat()
                if service.created_at
                else None,
            }
            for service in services
        ]
    }


@router.post("/api/services", status_code=201)
async def dashboard_create_service(
    request: DashboardServiceCreateRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Create a service for onboarding wizard via dashboard-scoped API."""
    from ..onboarding import checklist_store
    from ..services.models import ServiceCreate
    from ..services.store import get_service_catalog_store

    tenant_slug = tenant_slug_from_auth(auth)
    tenant_id = auth.tenant_id or "default"
    service_name = request.name.strip()
    if not service_name:
        raise HTTPException(status_code=400, detail="service_name_required")

    service = await get_service_catalog_store().create_service(
        ServiceCreate(name=service_name, metadata={"source": "manual"}),
        tenant_slug=tenant_slug,
    )

    await checklist_store.set_step(tenant_id, "add_services", True)
    return {
        "id": service.id,
        "name": service.name,
        "source": (service.metadata or {}).get("source", "manual"),
        "metadata": service.metadata or {},
        "created_at": service.created_at.isoformat() if service.created_at else None,
    }


@router.delete("/api/services/{service_id}", status_code=204)
async def dashboard_delete_service(
    service_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Delete a service for onboarding wizard via dashboard-scoped API."""
    from ..onboarding import checklist_store
    from ..services.store import get_service_catalog_store

    tenant_slug = tenant_slug_from_auth(auth)
    tenant_id = auth.tenant_id or "default"
    store = get_service_catalog_store()

    deleted = await store.delete_service(service_id, tenant_slug=tenant_slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="service_not_found")

    remaining = await store.list_services(tenant_slug=tenant_slug)
    await checklist_store.set_step(tenant_id, "add_services", bool(remaining))


@router.get("/api/onboarding/checklist")
async def get_onboarding_checklist(
    auth: AuthContext = Depends(get_auth_context),
):
    """Get current tenant onboarding checklist (auto-syncs from integrations)."""
    from ..onboarding import checklist_store

    tenant_id = auth.tenant_id or "default"

    # Auto-sync: check oauth_token_store + integration_configs and mark steps done
    providers: set[str] = set()
    try:
        from ..integrations.oauth_tokens import oauth_token_store
        for p in ("pagerduty", "slack", "github", "datadog"):
            tok = await oauth_token_store.get_token(tenant_id, p)
            if tok and tok.access_token:
                providers.add(p)
    except Exception:
        pass
    try:
        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        rows = db.client.table("integration_configs").select("type").eq(
            "tenant_id", tenant_id
        ).eq("is_active", True).execute()
        if rows.data:
            providers.update(r["type"] for r in rows.data if r.get("type"))
    except Exception:
        pass
    try:
        if "pagerduty" in providers or "opsgenie" in providers:
            await checklist_store.set_step(tenant_id, "connect_alerting", True)
        if "slack" in providers:
            await checklist_store.set_step(tenant_id, "connect_slack", True)
        if "github" in providers:
            await checklist_store.set_step(tenant_id, "connect_github", True)
        if "datadog" in providers:
            await checklist_store.set_step(tenant_id, "connect_datadog", True)
    except Exception as e:
        logger.warning(
            "onboarding_integration_sync_failed",
            error=str(e),
            error_type=type(e).__name__,
            tenant_id=tenant_id,
        )

    # Also sync services
    try:
        from ..services.store import get_service_catalog_store

        store = get_service_catalog_store()
        tenant_slug = tenant_slug_from_auth(auth)
        services = await store.list_services(tenant_slug=tenant_slug)
        if services:
            await checklist_store.set_step(tenant_id, "add_services", True)
    except Exception as e:
        logger.warning(
            "onboarding_service_sync_failed",
            error=str(e),
            error_type=type(e).__name__,
            tenant_id=tenant_id,
        )

    # Mark create_account done if authenticated
    if auth.user:
        await checklist_store.set_step(tenant_id, "create_account", True)

    checklist = await checklist_store.get(tenant_id)
    return checklist.to_dict()


@router.post("/api/onboarding/checklist/{step}")
async def set_onboarding_step(
    step: str,
    done: bool = True,
    auth: AuthContext = Depends(get_auth_context),
):
    """Mark an onboarding checklist step as done/undone."""
    from ..onboarding import checklist_store

    tenant_id = auth.tenant_id or "default"
    checklist = await checklist_store.set_step(tenant_id, step, done)
    return checklist.to_dict()


@router.get("/api/onboarding/status")
async def get_onboarding_status(
    auth: AuthContext = Depends(get_auth_context),
):
    """Return a lightweight status for the wizard UI."""
    tenant_id = auth.tenant_id or "default"

    # Check in-memory tenant store first
    tenant = auth.tenant
    integrations = tenant.integrations if tenant else {}

    def connected(name: str) -> bool:
        v = integrations.get(name)
        if not v:
            return False
        return bool(v.get("encrypted") if isinstance(v, dict) else v)

    result = {
        "pagerduty": connected("pagerduty"),
        "slack": connected("slack"),
        "github": connected("github"),
        "datadog": connected("datadog"),
    }

    # Check oauth_token_store (new normalized store used by generic OAuth flow)
    details: dict[str, dict] = {}
    try:
        from ..integrations.oauth_tokens import oauth_token_store
        for provider_name in result:
            if not result[provider_name]:
                token_rec = await oauth_token_store.get_token(tenant_id, provider_name)
                if token_rec and token_rec.access_token:
                    result[provider_name] = True
                    details[provider_name] = {
                        "scopes": token_rec.scopes,
                        "connected_at": token_rec.created_at.isoformat() if token_rec.created_at else "",
                    }
    except Exception as e:
        logger.warning("oauth_token_store_check_failed", error=str(e))

    # Also check Supabase integration_configs for OAuth connections
    try:
        from ..db.supabase_db import get_db
        from ..security.crypto import decrypt_json
        db = get_db(use_admin=True)
        rows = (
            db.client.table("integration_configs")
            .select("type,config")
            .eq("tenant_id", tenant_id)
            .eq("is_active", True)
            .execute()
        )
        if rows.data:
            for row in rows.data:
                provider = row.get("type")
                if provider and provider in result:
                    result[provider] = True
                    # Extract display info from encrypted config
                    try:
                        config = row.get("config", {})
                        encrypted = config.get("encrypted", "") if isinstance(config, dict) else ""
                        if encrypted:
                            decrypted = decrypt_json(encrypted)
                            oauth = decrypted.get("oauth", {})
                            team = oauth.get("team", {})
                            detail = {}
                            if team and isinstance(team, dict):
                                detail["workspace"] = team.get("name", "")
                            if decrypted.get("subdomain"):
                                detail["subdomain"] = decrypted["subdomain"]
                            if oauth.get("scope"):
                                detail["scopes"] = oauth["scope"]
                            detail["connected_at"] = decrypted.get("connected_at", "")
                            details[provider] = detail
                    except Exception:
                        details[provider] = {}
    except Exception as e:
        logger.warning(
            "onboarding_status_sync_failed",
            error=str(e),
            error_type=type(e).__name__,
            tenant_id=tenant_id,
        )

    return {
        "authenticated": True,
        "tenant": {"id": tenant_id},
        "integrations": result,
        "details": details,
    }


@router.post("/api/onboarding/test-integration/{provider}")
async def test_integration(
    provider: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Test an integration connection by making a lightweight API call."""
    tenant_id = auth.tenant_id or "default"

    try:
        from ..security.crypto import decrypt_json

        # Check integration_tokens first (generic OAuth flow), then integration_configs (legacy)
        oauth = {}
        decrypted = {}

        from ..integrations.oauth_tokens import oauth_token_store
        token_rec = await oauth_token_store.get_token(tenant_id, provider)
        if token_rec:
            oauth = {"access_token": token_rec.access_token}
            decrypted = {"oauth": oauth}
        else:
            rows = None
            try:
                from ..db.supabase_db import get_db

                db = get_db(use_admin=True)
                rows = db.client.table("integration_configs").select("config").eq(
                    "tenant_id", tenant_id
                ).eq("type", provider).eq("is_active", True).limit(1).execute()
            except Exception as exc:
                logger.warning("integration_config_lookup_failed", provider=provider, error=str(exc))

            if rows and rows.data:
                config = rows.data[0].get("config", {})
                encrypted = config.get("encrypted", "") if isinstance(config, dict) else ""
                if encrypted:
                    decrypted = decrypt_json(encrypted)
                oauth = decrypted.get("oauth", {})
            elif provider != "pagerduty":
                raise HTTPException(status_code=404, detail=f"{provider} not connected")

        if provider == "pagerduty":
            import httpx

            oauth_token = oauth.get("access_token", "")
            api_key = decrypted.get("api_key", "")
            subdomain = decrypted.get("subdomain")

            def _legacy_scopes() -> list[str]:
                raw = oauth.get("scope")
                if isinstance(raw, str):
                    return [s.strip() for s in raw.replace(",", " ").split(" ") if s.strip()]
                if isinstance(raw, list):
                    return [str(s).strip() for s in raw if str(s).strip()]
                return []

            details = {
                "subdomain": subdomain,
                "scopes": token_rec.scopes if token_rec else _legacy_scopes(),
                "connected_at": decrypted.get("connected_at") or (token_rec.created_at.isoformat() if token_rec else None),
            }

            async def _fetch_pd_subdomain(access_token: str) -> str | None:
                """Fetch PagerDuty account subdomain via /services (we have services_read scope)."""
                try:
                    async with httpx.AsyncClient(timeout=10) as hc:
                        resp = await hc.get(
                            "https://api.pagerduty.com/services?limit=1",
                            headers={
                                "Authorization": f"Bearer {access_token}",
                                "Accept": "application/vnd.pagerduty+json;version=2",
                            },
                        )
                        if resp.status_code == 200:
                            services = resp.json().get("services", [])
                            if services:
                                html_url = services[0].get("html_url", "")
                                # html_url: https://acme.pagerduty.com/services/PXXXXXX
                                if "pagerduty.com" in html_url:
                                    from urllib.parse import urlparse
                                    host = urlparse(html_url).hostname or ""
                                    sub = host.replace(".pagerduty.com", "")
                                    if sub and sub != "app":
                                        return sub
                        else:
                            logger.warning("pagerduty_services_status", status=resp.status_code, body=resp.text[:200])
                except Exception as exc:
                    logger.warning("pagerduty_subdomain_fetch_failed", error=str(exc))
                return None

            # Prefer normalized OAuth token store record.
            if token_rec and token_rec.access_token:
                now = datetime.now(UTC)
                if not token_rec.token_expiry or token_rec.token_expiry > now:
                    if not details.get("subdomain"):
                        details["subdomain"] = await _fetch_pd_subdomain(token_rec.access_token)
                    return {"ok": True, "details": details}

                # Expired token: attempt refresh.
                from ..integrations.oauth_providers import get_provider_credentials

                if not token_rec.refresh_token:
                    return {"ok": False, "details": "PagerDuty token is expired and refresh failed"}

                client_id, client_secret = get_provider_credentials("pagerduty")
                if not client_id or not client_secret:
                    return {"ok": False, "details": "PagerDuty token is expired and refresh failed"}

                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        refresh_resp = await client.post(
                            "https://identity.pagerduty.com/oauth/token",
                            data={
                                "grant_type": "refresh_token",
                                "refresh_token": token_rec.refresh_token,
                                "client_id": client_id,
                                "client_secret": client_secret,
                            },
                            headers={"Accept": "application/json"},
                        )
                except Exception as exc:
                    logger.warning("pagerduty_refresh_error", error=str(exc))
                    return {"ok": False, "details": "PagerDuty token is expired and refresh failed"}

                if refresh_resp.status_code != 200:
                    return {"ok": False, "details": "PagerDuty token is expired and refresh failed"}

                new_tokens = refresh_resp.json()
                new_access_token = new_tokens.get("access_token", "")
                if not new_access_token:
                    return {"ok": False, "details": "PagerDuty token is expired and refresh failed"}

                new_expiry = None
                try:
                    expires_in = new_tokens.get("expires_in")
                    expires_in_value = int(expires_in) if expires_in is not None else None
                except (TypeError, ValueError):
                    expires_in_value = None
                if expires_in_value and expires_in_value > 0:
                    new_expiry = datetime.now(UTC) + timedelta(seconds=expires_in_value)

                new_scope = new_tokens.get("scope")
                if isinstance(new_scope, str):
                    new_scopes = [s.strip() for s in new_scope.replace(",", " ").split(" ") if s.strip()]
                else:
                    new_scopes = token_rec.scopes

                updated = await oauth_token_store.upsert_token(
                    tenant_id=tenant_id,
                    provider="pagerduty",
                    access_token=new_access_token,
                    refresh_token=new_tokens.get("refresh_token", token_rec.refresh_token),
                    token_expiry=new_expiry,
                    scopes=new_scopes,
                )
                details["scopes"] = updated.scopes
                details["refreshed_at"] = datetime.now(UTC).isoformat()
                return {"ok": True, "details": details}

            # Legacy config path: accept configured OAuth/API key as connected.
            if oauth_token or api_key:
                return {"ok": True, "details": details}

            return {"ok": False, "details": "PagerDuty is not connected"}

        elif provider == "slack":
            import httpx

            token = oauth.get("access_token", "")
            team = oauth.get("team", {})
            team_name = team.get("name", "unknown") if isinstance(team, dict) else "unknown"
            if not token:
                return {"ok": True, "details": f"Connected to {team_name} (no token to verify)"}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {token}"},
                )
            data = resp.json()
            if data.get("ok"):
                return {"ok": True, "details": f"Slack — {data.get('team', team_name)} as {data.get('user', 'bot')}"}
            return {"ok": False, "details": f"Slack auth.test failed: {data.get('error', 'unknown')}"}

        elif provider == "github":
            import httpx

            token = decrypted.get("token") or oauth.get("access_token", "")
            if not token:
                return {"ok": True, "details": "GitHub connected (no token to verify)"}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                )
            if resp.status_code == 200:
                user = resp.json()
                return {"ok": True, "details": f"GitHub — authenticated as {user.get('login', 'unknown')}"}
            return {"ok": False, "details": f"GitHub API returned {resp.status_code}"}

        elif provider == "datadog":
            import httpx

            api_key = decrypted.get("api_key", "")
            app_key = decrypted.get("app_key", "")
            if not api_key:
                return {"ok": True, "details": "Datadog connected (no key to verify)"}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.datadoghq.com/api/v1/validate",
                    headers={"DD-API-KEY": api_key, "DD-APPLICATION-KEY": app_key},
                )
            if resp.status_code == 200:
                return {"ok": True, "details": "Datadog — API key valid"}
            return {"ok": False, "details": f"Datadog returned {resp.status_code}"}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("test_integration_failed", provider=provider, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/onboarding/integrations/pagerduty/import-services")
async def import_pagerduty_services(
    auth: AuthContext = Depends(get_auth_context),
):
    """Import services from the connected PagerDuty account."""
    tenant_id = auth.tenant_id or "default"

    try:
        # Try oauth_token_store first (new normalized store), then legacy integration_configs
        from ..integrations.oauth_tokens import oauth_token_store

        token_rec = await oauth_token_store.get_token(tenant_id, "pagerduty")
        oauth_token = ""
        api_key = ""

        if token_rec and token_rec.access_token:
            oauth_token = token_rec.access_token
        else:
            try:
                from ..db.supabase_db import get_db
                from ..security.crypto import decrypt_json

                db = get_db(use_admin=True)
                rows = db.client.table("integration_configs").select("config").eq(
                    "tenant_id", tenant_id
                ).eq("type", "pagerduty").eq("is_active", True).limit(1).execute()

                if rows.data:
                    config = rows.data[0].get("config", {})
                    encrypted = config.get("encrypted", "") if isinstance(config, dict) else ""
                    if encrypted:
                        decrypted = decrypt_json(encrypted)
                        oauth = decrypted.get("oauth", {})
                        oauth_token = oauth.get("access_token", "")
                        api_key = decrypted.get("api_key", "")
            except Exception as exc:
                logger.warning("import_services_legacy_lookup_failed", error=str(exc))

        token = oauth_token or api_key
        if not token:
            raise HTTPException(status_code=404, detail="PagerDuty not connected")

        # PagerDuty uses "Bearer" for OAuth tokens, "Token token=" for API keys
        if oauth_token:
            pd_auth = f"Bearer {oauth_token}"
        else:
            pd_auth = f"Token token={api_key}"

        # Fetch services from PagerDuty API
        import httpx

        imported = 0
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.pagerduty.com/services",
                headers={
                    "Authorization": pd_auth,
                    "Content-Type": "application/json",
                    "Accept": "application/vnd.pagerduty+json;version=2",
                },
                params={"limit": 100},
            )
            if resp.status_code != 200:
                logger.warning("import_pd_services_api_error", status=resp.status_code, body=resp.text[:500])
                return {"ok": False, "error": f"PagerDuty API returned {resp.status_code}", "details": resp.text[:200]}

            pd_services = resp.json().get("services", [])

        # Import into service catalog
        from ..services.models import ServiceCreate, ServiceCriticality
        from ..services.store import get_service_catalog_store

        store = get_service_catalog_store()
        tenant_slug = tenant_slug_from_auth(auth)

        for pd_svc in pd_services:
            name = pd_svc.get("name", "").strip()
            if not name:
                continue
            req = ServiceCreate(
                name=name,
                description=pd_svc.get("description") or f"Imported from PagerDuty",
                team=pd_svc.get("teams", [{}])[0].get("summary") if pd_svc.get("teams") else None,
                criticality=ServiceCriticality.CRITICAL if pd_svc.get("alert_creation") == "create_alerts_and_incidents" else ServiceCriticality.MEDIUM,
                metadata={
                    "source": "pagerduty",
                    "pagerduty_id": pd_svc.get("id"),
                    "pagerduty_url": pd_svc.get("html_url"),
                },
            )
            await store.create_service(req, tenant_slug=tenant_slug)
            imported += 1

        # Mark onboarding step done
        from ..onboarding import checklist_store
        await checklist_store.set_step(tenant_id, "add_services", True)

        return {"ok": True, "imported": imported, "total_pd_services": len(pd_services)}

    except HTTPException as he:
        logger.warning("import_pagerduty_services_http_error", status=he.status_code, detail=he.detail)
        return {"ok": False, "error": he.detail}
    except Exception as exc:
        logger.warning("import_pagerduty_services_failed", error=str(exc), error_type=type(exc).__name__)
        return {"ok": False, "error": str(exc)}


@router.post("/api/integrations/pagerduty/sync")
async def sync_pagerduty_incidents(
    auth: AuthContext = Depends(get_auth_context),
):
    """Pull recent incidents from PagerDuty and persist to incident store."""
    tenant_id = auth.tenant_id or "default"

    try:
        # Resolve PagerDuty token — same pattern as import_pagerduty_services
        from ..integrations.oauth_tokens import oauth_token_store

        token_rec = await oauth_token_store.get_token(tenant_id, "pagerduty")
        oauth_token = ""
        api_key = ""

        if token_rec and token_rec.access_token:
            oauth_token = token_rec.access_token
        else:
            try:
                from ..db.supabase_db import get_db
                from ..security.crypto import decrypt_json

                db = get_db(use_admin=True)
                rows = db.client.table("integration_configs").select("config").eq(
                    "tenant_id", tenant_id
                ).eq("type", "pagerduty").eq("is_active", True).limit(1).execute()

                if rows.data:
                    config = rows.data[0].get("config", {})
                    encrypted = config.get("encrypted", "") if isinstance(config, dict) else ""
                    if encrypted:
                        decrypted = decrypt_json(encrypted)
                        oauth = decrypted.get("oauth", {})
                        oauth_token = oauth.get("access_token", "")
                        api_key = decrypted.get("api_key", "")
            except Exception as exc:
                logger.warning("sync_incidents_legacy_lookup_failed", error=str(exc))

        token = oauth_token or api_key
        if not token:
            raise HTTPException(status_code=404, detail="PagerDuty not connected")

        if oauth_token:
            pd_auth = f"Bearer {oauth_token}"
        else:
            pd_auth = f"Token token={api_key}"

        # Fetch recent incidents from PagerDuty API
        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.pagerduty.com/incidents",
                headers={
                    "Authorization": pd_auth,
                    "Content-Type": "application/json",
                    "Accept": "application/vnd.pagerduty+json;version=2",
                },
                params={
                    "statuses[]": ["triggered", "acknowledged", "resolved"],
                    "sort_by": "created_at:desc",
                    "limit": 25,
                },
            )
            if resp.status_code != 200:
                logger.warning("sync_pd_incidents_api_error", status=resp.status_code, body=resp.text[:500])
                return {"ok": False, "error": f"PagerDuty API returned {resp.status_code}", "details": resp.text[:200]}

            pd_incidents = resp.json().get("incidents", [])

        synced = 0
        incident_summaries = []

        for inc in pd_incidents:
            inc_id = inc.get("id", "")
            if not inc_id:
                continue

            urgency = inc.get("urgency", "low")
            severity = Severity.HIGH if urgency == "high" else Severity.LOW

            service_summary = ""
            svc = inc.get("service")
            if isinstance(svc, dict):
                service_summary = svc.get("summary", "")

            created_at_str = inc.get("created_at", "")
            try:
                triggered_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                triggered_at = datetime.now(UTC)

            # Build assigned_to list
            assigned_to = []
            for assignment in inc.get("assignments", []):
                assignee = assignment.get("assignee", {})
                if isinstance(assignee, dict) and assignee.get("summary"):
                    assigned_to.append(assignee["summary"])

            # Escalation policy
            ep = inc.get("escalation_policy", {})
            ep_summary = ep.get("summary", "") if isinstance(ep, dict) else ""

            metadata = {
                "provider": "pagerduty",
                "status": inc.get("status", ""),
                "urgency": urgency,
                "assigned_to": assigned_to,
                "escalation_policy": ep_summary,
            }

            await incident_store.add_incident(
                incident_id=inc_id,
                title=inc.get("title", ""),
                service_name=service_summary,
                severity=severity,
                triggered_at=triggered_at,
                source="pagerduty",
                source_url=inc.get("html_url", ""),
                source_id=str(inc.get("incident_number", "")),
                metadata=metadata,
                tenant_id=tenant_id,
            )

            # If resolved, mark as completed
            if inc.get("status") == "resolved":
                await incident_store.complete_incident(
                    inc_id,
                    ContextCard(
                        incident_id=inc_id,
                        title=inc.get("title", ""),
                        severity=severity,
                        service_name=service_summary,
                        triggered_at=triggered_at,
                        assembled_at=datetime.now(UTC),
                        assembly_time_ms=0,
                    ),
                    metadata={"resolved_via_sync": True},
                    tenant_id=tenant_id,
                )

            synced += 1
            incident_summaries.append({
                "id": inc_id,
                "title": inc.get("title", ""),
                "status": inc.get("status", ""),
            })

        return {"ok": True, "synced": synced, "incidents": incident_summaries}

    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("sync_pagerduty_incidents_failed", error=str(exc), error_type=type(exc).__name__)
        return {"ok": False, "error": str(exc)}


@router.get("/api/integrations/pagerduty/sync/status")
async def pagerduty_sync_status(
    auth: AuthContext = Depends(get_auth_context),
):
    """Return PagerDuty sync connection status."""
    tenant_id = auth.tenant_id or "default"

    connected = False
    try:
        from ..integrations.oauth_tokens import oauth_token_store

        token_rec = await oauth_token_store.get_token(tenant_id, "pagerduty")
        if token_rec and token_rec.access_token:
            connected = True
    except Exception:
        pass

    if not connected:
        try:
            from ..db.supabase_db import get_db
            from ..security.crypto import decrypt_json

            db = get_db(use_admin=True)
            rows = db.client.table("integration_configs").select("config").eq(
                "tenant_id", tenant_id
            ).eq("type", "pagerduty").eq("is_active", True).limit(1).execute()

            if rows.data:
                config = rows.data[0].get("config", {})
                encrypted = config.get("encrypted", "") if isinstance(config, dict) else ""
                if encrypted:
                    decrypted = decrypt_json(encrypted)
                    oauth = decrypted.get("oauth", {})
                    if oauth.get("access_token") or decrypted.get("api_key"):
                        connected = True
        except Exception:
            pass

    return {"connected": connected, "last_sync": None}


@router.post("/api/onboarding/integrations/github")
async def save_github_integration(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
):
    """Save GitHub PAT and org for deploy and repo context."""
    tenant_id = auth.tenant_id or "default"
    body = await request.json()
    token_val = body.get("token", "").strip()
    org = body.get("org", "").strip()

    if not token_val:
        raise HTTPException(status_code=400, detail="GitHub token is required")

    try:
        from ..db.supabase_db import get_db
        from ..security.crypto import encrypt_json

        db = get_db(use_admin=True)
        encrypted = encrypt_json({"token": token_val, "org": org})
        db.client.table("integration_configs").upsert({
            "tenant_id": tenant_id,
            "type": "github",
            "config": {"encrypted": encrypted},
            "is_active": True,
        }, on_conflict="tenant_id,type").execute()

        from ..onboarding import checklist_store
        await checklist_store.set_step(tenant_id, "connect_github", True)

        return {"ok": True, "provider": "github"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("save_github_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/onboarding/integrations/datadog")
async def save_datadog_integration(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
):
    """Save Datadog API/App keys."""
    tenant_id = auth.tenant_id or "default"
    body = await request.json()
    api_key = body.get("api_key", "").strip()
    app_key = body.get("app_key", "").strip()
    site = body.get("site", "datadoghq.com").strip()

    if not api_key:
        raise HTTPException(status_code=400, detail="Datadog API key is required")

    try:
        from ..db.supabase_db import get_db
        from ..security.crypto import encrypt_json

        db = get_db(use_admin=True)
        encrypted = encrypt_json({"api_key": api_key, "app_key": app_key, "site": site})
        db.client.table("integration_configs").upsert({
            "tenant_id": tenant_id,
            "type": "datadog",
            "config": {"encrypted": encrypted},
            "is_active": True,
        }, on_conflict="tenant_id,type").execute()

        from ..onboarding import checklist_store
        await checklist_store.set_step(tenant_id, "connect_datadog", True)

        return {"ok": True, "provider": "datadog"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("save_datadog_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/onboarding/test-incident/{incident_id}")
async def get_test_incident_status(
    incident_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Poll for test incident processing status."""
    try:
        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        rows = db.client.table("incidents").select("id,status,title,verdict").eq(
            "id", incident_id
        ).limit(1).execute()

        if not rows.data:
            return {"incident_id": incident_id, "status": "processing"}

        incident = rows.data[0]
        status = "completed" if incident.get("verdict") else "processing"
        return {
            "incident_id": incident_id,
            "status": status,
            "title": incident.get("title"),
            "verdict": incident.get("verdict"),
        }
    except Exception:
        return {"incident_id": incident_id, "status": "processing"}


@router.post("/api/onboarding/disconnect/{provider}")
async def disconnect_integration(
    provider: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Disconnect an OAuth integration."""
    tenant_id = auth.tenant_id or "default"
    try:
        # Remove from oauth_token_store
        try:
            from ..integrations.oauth_tokens import oauth_token_store
            await oauth_token_store.delete_token(tenant_id, provider)
        except Exception:
            pass  # store may not have this token

        # Remove from legacy integration_configs
        try:
            from ..db.supabase_db import get_db
            db = get_db(use_admin=True)
            db.client.table("integration_configs").delete().eq(
                "tenant_id", tenant_id
            ).eq("type", provider).execute()
        except Exception:
            pass

        return {"ok": True, "provider": provider}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/onboarding/test-incident")
async def run_onboarding_test_incident(
    service_name: str = "payments-api",
    auth: AuthContext = Depends(get_auth_context),
):
    """Start a synthetic incident to validate the pipeline."""
    from ..models import Severity
    from ..onboarding import checklist_store
    from ..onboarding.test_incident import start_test_incident

    tenant_id = auth.tenant_id or "default"

    incident_id = await start_test_incident(
        service_name=service_name,
        severity=Severity.HIGH,
        tenant_id=tenant_id,
    )

    await checklist_store.set_step(tenant_id, "run_test", True)

    return {"incident_id": incident_id, "status": "processing"}


# Demo data generation
DEMO_SERVICES = [
    "payments-api",
    "user-service",
    "notification-service",
    "checkout-api",
    "inventory-service",
]
DEMO_TITLES = [
    "High error rate detected",
    "Latency spike in production",
    "Database connection pool exhausted",
    "Memory usage critical",
    "Failed health checks",
    "Increased 5xx responses",
    "Queue processing delay",
    "Certificate expiring soon",
]


@router.post("/api/demo")
async def create_demo_incident():
    """Create a demo incident for testing."""
    incident_id = str(uuid.uuid4())
    service = random.choice(DEMO_SERVICES)
    severity = random.choice(list(Severity))
    title = f"{random.choice(DEMO_TITLES)} in {service}"
    triggered_at = datetime.utcnow()

    # Add incident in processing state
    await incident_store.add_incident(
        incident_id=incident_id,
        title=title,
        service_name=service,
        severity=severity,
        triggered_at=triggered_at,
    )

    # Simulate async processing
    asyncio.create_task(
        _process_demo_incident(incident_id, service, severity, title, triggered_at)
    )

    return {"incident_id": incident_id, "status": "processing"}


async def _process_demo_incident(
    incident_id: str,
    service: str,
    severity: Severity,
    title: str,
    triggered_at: datetime,
):
    """Simulate incident processing with demo data."""
    # Simulate processing time
    await asyncio.sleep(random.uniform(1.5, 3.5))

    # Randomly fail some incidents for realism
    if random.random() < 0.1:  # 10% failure rate
        await incident_store.fail_incident(
            incident_id,
            "Simulated failure: Could not fetch context from external services",
        )
        return

    # Generate demo context card
    now = datetime.utcnow()

    # Demo deployments
    deploys = [
        Deployment(
            sha=f"{random.randint(0, 0xFFFFFFFF):08x}" * 5,
            short_sha=f"{random.randint(0, 0xFFFFFF):06x}",
            author=random.choice(["alice", "bob", "charlie", "diana"]),
            message=random.choice(
                [
                    "Fix connection pooling issue",
                    "Update dependencies",
                    "Add retry logic for external calls",
                    "Optimize database queries",
                    "Enable feature flag for new flow",
                ]
            ),
            timestamp=now - timedelta(hours=random.randint(1, 48)),
            files_changed=[f"src/{service.replace('-', '/')}/main.py"],
            additions=random.randint(10, 200),
            deletions=random.randint(5, 50),
        )
        for _ in range(random.randint(2, 5))
    ]

    github_ctx = GitHubContext(
        repo=f"mycompany/{service}",
        recent_deploys=deploys,
        codeowners=["@platform-team", "@oncall"],
    )

    # Demo Datadog context
    datadog_ctx = DatadogContext(
        service=service,
        logs=[],
        log_summaries=[
            LogSummary(
                pattern="Connection timeout to database",
                count=random.randint(50, 500),
                level="ERROR",
                sample_message="FATAL: connection to database 'prod-db' failed: timeout",
            ),
            LogSummary(
                pattern="Request processing slow",
                count=random.randint(100, 1000),
                level="WARN",
                sample_message="Request took 5234ms to complete",
            ),
        ],
        metrics=MetricSnapshot(
            error_rate=random.uniform(0.5, 15.0),
            error_rate_baseline=0.1,
            latency_p99_ms=random.uniform(200, 2000),
            request_count=random.randint(10000, 100000),
        ),
    )

    # Demo AI summary
    ai_summary = AILogSummary(
        top_issues=[
            "Database connection timeouts increased 10x in the last hour",
            "Error rate spiked following deployment abc123",
            "Memory pressure detected on primary database node",
        ],
        explanation="The service is experiencing elevated error rates primarily due to database connectivity issues. "
        "Connection pool exhaustion appears to be the root cause, possibly triggered by a recent deployment "
        "that increased query volume or changed connection handling.",
        likely_cause="Database connection pool exhaustion following increased traffic after deployment",
        suggested_actions=[
            "Check database connection pool settings and increase if needed",
            "Review recent deployment changes for connection handling modifications",
            "Consider enabling connection pooler (PgBouncer) if not already in use",
            "Scale database resources if connection limits are being hit",
        ],
    )

    # Create context card
    card = ContextCard(
        incident_id=incident_id,
        title=title,
        severity=severity,
        service_name=service,
        triggered_at=triggered_at,
        alert_url=f"https://pagerduty.com/incidents/{incident_id}",
        github=github_ctx,
        datadog=datadog_ctx,
        ai_summary=ai_summary,
        similar_incidents=[],
        owners=["@platform-team", "@oncall"],
        runbook_url=f"https://wiki.internal/runbooks/{service}",
        dashboard_url=f"https://datadog.com/dashboards/{service}",
        assembled_at=now,
        assembly_time_ms=random.randint(800, 2500),
        errors=[],
    )

    await incident_store.complete_incident(incident_id, card)


@router.get("/demo", response_class=HTMLResponse)
async def demo_page(request: Request):
    """Interactive demo page for showcasing Incident Copilot."""
    from ..demo.scenarios import list_scenarios

    scenarios = list_scenarios()

    return templates.TemplateResponse(
        "demo.html",
        {
            "request": request,
            "scenarios": scenarios,
            "page_title": "Demo Mode",
        },
    )


@router.get("/insights", response_class=HTMLResponse)
async def insights_page(request: Request):
    """AI Insights and Pattern Detection dashboard."""
    return templates.TemplateResponse(
        "insights.html",
        {
            "request": request,
            "page_title": "Insights",
        },
    )


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    """Analytics dashboard showing MTTR and incident metrics."""
    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "page_title": "Analytics",
        },
    )
