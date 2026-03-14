"""Landing/auth/core API routes extracted from legacy dashboard router module."""

import asyncio
import json

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from ...auth.middleware import AuthContext, get_auth_context
from ...auth.models import Tenant, User
from ..store import incident_store
from .common import (
    _map_status,
    landing_router,
    logger,
    require_dashboard_auth,
    router,
    templates,
)


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


# Canonical incidents API routes live in src/api/incidents.py.


@landing_router.get("/api/dashboard/stats")
async def api_dashboard_stats(
    request: Request,
    auth_data: dict[str, str] = Depends(require_dashboard_auth),
):
    """Tenant-scoped JSON API endpoint for dashboard stats."""
    tenant_id = auth_data["tenant_id"]

    from ...supabase_client import is_supabase_db_enabled

    if not is_supabase_db_enabled():
        return await incident_store.get_stats()

    # Compute stats from incidents list
    from ...db.supabase_db import get_db
    from ...models import Severity

    db = get_db(use_admin=True)
    rows = await db.list_processing_incidents(tenant_id=tenant_id, limit=100, offset=0)

    by_status: dict[str, int] = {
        "triggered": 0,
        "acknowledged": 0,
        "resolved": 0,
        "error": 0,
        # Backward compatibility for existing dashboard consumers.
        "processing": 0,
        "completed": 0,
    }
    by_severity: dict[str, int] = {s.value: 0 for s in Severity}

    for r in rows:
        st = _map_status(r.get("status") or "processing")
        by_status[st] = by_status.get(st, 0) + 1
        if st == "resolved":
            by_status["completed"] += 1
        elif st in ("triggered", "acknowledged"):
            by_status["processing"] += 1
        elif st == "error":
            by_status["error"] += 1
        sev = r.get("severity") or Severity.MEDIUM.value
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {"total": len(rows), "by_status": by_status, "by_severity": by_severity}


@landing_router.get("/auth/callback", response_class=HTMLResponse)
async def auth_callback(request: Request):
    """Handle Supabase Auth PKCE callback.

    Supabase redirects here with ?code=xxx after OAuth.
    The code exchange must happen client-side where the PKCE code verifier
    is stored (in the browser's storage from the initial OAuth request).
    """
    return HTMLResponse(content="""
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
                    // User hasn't signed up yet - reject login
                    localStorage.removeItem('access_token');
                    localStorage.removeItem('refresh_token');
                    localStorage.removeItem('user');
                    localStorage.removeItem('tenant_id');
                    window.location.href = '/login?error=no_account';
                } else if (flow === 'signup' && !data.has_profile) {
                    // New signup - send to onboarding
                    window.location.href = '/dashboard/onboarding-wizard';
                } else {
                    // Existing user - go to dashboard
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
""")


@landing_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    """Login page."""
    from ...auth.oauth import get_available_providers
    from ...supabase_client import is_supabase_auth_enabled

    error_messages = {
        "no_account": "No account found. Please sign up first.",
        "session_expired": "Your session has expired. Please sign in again.",
        "oauth_denied": "You cancelled the login process.",
        "oauth_invalid": "Invalid OAuth response. Please try again.",
        "oauth_invalid_state": "Session expired. Please try again.",
        "oauth_not_configured": "This login method is not configured.",
        "oauth_token_failed": "Failed to authenticate. Please try again.",
        "oauth_user_failed": "Failed to get user info. Please try again.",
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
    from ...auth.oauth import get_available_providers
    from ...supabase_client import is_supabase_auth_enabled

    return templates.TemplateResponse(
        "signup.html",
        {
            "request": request,
            "providers": get_available_providers(),
            "supabase_auth_enabled": is_supabase_auth_enabled(),
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
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: list[str] | None = Query(None),
    severity: list[str] | None = Query(None),
    service: list[str] | None = Query(None),
    team: list[str] | None = Query(None),
    assignee: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    search: str | None = Query(None),
    auth_data: dict[str, str] = Depends(require_dashboard_auth),
):
    """Backward-compatible tenant-scoped incidents endpoint under /dashboard."""
    from ...api.incidents import list_incidents

    tenant_id = auth_data["tenant_id"]
    user_id = auth_data["user_id"]
    return await list_incidents(
        request=request,
        page=page,
        limit=limit,
        status=status,
        severity=severity,
        service=service,
        team=team,
        assignee=assignee,
        date_from=date_from,
        date_to=date_to,
        search=search,
        auth=AuthContext(
            user=User(
                id=user_id,
                email=f"{user_id}@dashboard.local",
                name=user_id,
                tenant_id=tenant_id,
            ),
            tenant=Tenant(id=tenant_id, name=tenant_id, slug=tenant_id),
        ),
    )


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
        from ...db.supabase_db import get_db

        db = get_db(use_admin=True)
        update_data: dict = {"status": canonical_status}
        if canonical_status == "completed":
            from datetime import datetime

            update_data["processed_at"] = datetime.now(UTC).isoformat()
        elif canonical_status == "processing":
            update_data["processed_at"] = None

        await db._to_thread(
            lambda: db.client.table("incidents")
            .update(update_data)
            .eq("id", incident_id)
            .eq("tenant_id", tenant_id)
            .execute()
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
