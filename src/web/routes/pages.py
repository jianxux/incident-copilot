"""Dashboard HTML rendering routes and incident page endpoints."""

from datetime import UTC, datetime

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ...config import get_settings
from ..store import incident_store
from .common import require_dashboard_auth, router, templates


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
    """Legacy onboarding - redirect to unified wizard."""
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
    from ..timeline import TimelineBuilder, TimelineEventType, format_duration

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
        "errors": len([e for e in events if e.event_type == TimelineEventType.LOG_ERROR]),
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
    from ..timeline import TimelineBuilder

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
