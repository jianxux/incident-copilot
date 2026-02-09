"""Web routes for the Incident Copilot dashboard."""

import asyncio
import json
import random
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth.middleware import AuthContext, get_auth_context
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

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

# Set up templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Landing page router (root path)
landing_router = APIRouter(tags=["landing"])

# Dashboard router
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


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
        Severity.LOW: "bg-blue-500",
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


# Add template filters
templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["severity_color"] = severity_color
templates.env.filters["status_color"] = status_color
templates.env.filters["mask_secret"] = mask_secret


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


# ============================================================================
# Auth Pages (login, signup, etc.)
# ============================================================================


@landing_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    """Login page."""
    from ..auth.oauth import get_available_providers
    from ..supabase_client import is_supabase_auth_enabled

    error_messages = {
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
    """Main dashboard page showing all incidents."""
    incidents = await incident_store.get_all_incidents()
    stats = await incident_store.get_stats()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "incidents": incidents,
            "stats": stats,
            "page_title": "Dashboard",
        },
    )


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request):
    """Legacy onboarding page (manual API keys)."""
    settings = get_settings()

    webhook_url = f"{settings.app_url}/webhooks/pagerduty"

    return templates.TemplateResponse(
        "onboarding.html",
        {
            "request": request,
            "page_title": "Setup",
            "webhook_url": webhook_url,
        },
    )


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


@router.get("/incident/{incident_id}", response_class=HTMLResponse)
async def incident_detail(request: Request, incident_id: str):
    """Incident detail page showing full context card."""
    incident = await incident_store.get_incident(incident_id)

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


@router.get("/incident/{incident_id}/timeline", response_class=HTMLResponse)
async def incident_timeline(request: Request, incident_id: str):
    """Interactive timeline view for an incident."""
    from .timeline import TimelineBuilder, TimelineEventType, format_duration

    incident = await incident_store.get_incident(incident_id)

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
async def api_incidents():
    """JSON API endpoint for incidents list."""
    incidents = await incident_store.get_all_incidents()
    return {
        "incidents": [
            {
                "incident_id": i.incident_id,
                "title": i.title,
                "service_name": i.service_name,
                "severity": i.severity.value,
                "status": i.status,
                "triggered_at": i.triggered_at.isoformat(),
                "processed_at": i.processed_at.isoformat() if i.processed_at else None,
            }
            for i in incidents
        ]
    }


@router.get("/api/stats")
async def api_stats():
    """JSON API endpoint for dashboard stats."""
    return await incident_store.get_stats()


# =========================================================================
# Onboarding APIs
# =========================================================================


@router.get("/api/onboarding/checklist")
async def get_onboarding_checklist(
    auth: AuthContext = Depends(get_auth_context),
):
    """Get current tenant onboarding checklist."""
    from ..onboarding.checklist import checklist_store

    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required"
        )

    checklist = checklist_store.get(auth.tenant_id)
    return checklist.to_dict()


@router.post("/api/onboarding/checklist/{step}")
async def set_onboarding_step(
    step: str,
    done: bool = True,
    auth: AuthContext = Depends(get_auth_context),
):
    """Mark an onboarding checklist step as done/undone."""
    from ..onboarding.checklist import checklist_store

    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required"
        )

    checklist = checklist_store.set_step(auth.tenant_id, step, done)
    return checklist.to_dict()


@router.get("/api/onboarding/status")
async def get_onboarding_status(
    auth: AuthContext = Depends(get_auth_context),
):
    """Return a lightweight status for the wizard UI."""
    if not auth.tenant_id:
        return {"authenticated": False}

    tenant = auth.tenant
    integrations = tenant.integrations if tenant else {}

    def connected(name: str) -> bool:
        v = integrations.get(name)
        if not v:
            return False
        # We store encrypted records under {encrypted: "..."}.
        return bool(v.get("encrypted") if isinstance(v, dict) else v)

    return {
        "authenticated": True,
        "tenant": {"id": auth.tenant_id},
        "integrations": {
            "pagerduty": connected("pagerduty"),
            "slack": connected("slack"),
            "github": connected("github"),
            "datadog": connected("datadog"),
        },
    }


@router.post("/api/onboarding/test-incident")
async def run_onboarding_test_incident(
    service_name: str = "payments-api",
    auth: AuthContext = Depends(get_auth_context),
):
    """Start a synthetic incident to validate the pipeline."""
    from ..models import Severity
    from ..onboarding.checklist import checklist_store
    from ..onboarding.test_incident import start_test_incident

    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required"
        )

    incident_id = await start_test_incident(
        service_name=service_name,
        severity=Severity.HIGH,
    )

    checklist_store.set_step(auth.tenant_id, "run_test", True)

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
