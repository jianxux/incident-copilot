"""Main FastAPI application for Incident Copilot."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import (
    ai_feedback_router,
    analytics_router,
    correlation_router,
    demo_router,
    email_router,
    health_router,
    incidents_router,
    insights_router,
    predictive_insights_router,
    latency_router,
    memory_advanced_router,
    memory_feedback_router,
    memory_stats_router,
    metrics_router,
    onboarding_router,
    oncall_handoff_router,
    pagerduty_sync_router,
    plugins_router,
    postmortem_router,
    runbooks_router,
    webhooks_router,
)
from .api.audit import router as audit_router
from .api.copilot import router as copilot_router
from .api.demo_trigger import router as demo_trigger_router
from .api.health import set_app_start_time
from .api.oauth_integrations import router as oauth_integrations_router
from .audit.middleware import AuditMiddleware
from .audit.store import audit_store
from .auth.oauth_pagerduty import router as pagerduty_oauth_router
from .auth.oauth_slack import router as slack_oauth_router
from .auth.routes import router as auth_router
from .auth.sso.routes import router as sso_router
from .auth.supabase_auth import router as supabase_auth_router
from .actions.routes import router as actions_router
from .billing.routes import router as billing_router
from .config import get_settings
from .copilot.adapters.slack_adapter import router as slack_copilot_router
from .copilot.adapters.teams_adapter import router as teams_copilot_router
from .copilot.adapters.web_adapter import router as web_copilot_router
from .db.migrate import run_pending_migrations
from .metrics import HEALTH_STATUS, set_app_info
from .metrics.middleware import PrometheusMiddleware
from .oncall.scheduler import (
    start_oncall_handoff_scheduler,
    stop_oncall_handoff_scheduler,
)
from .ratelimit.middleware import RateLimitMiddleware
from .ratelimit.routes import router as ratelimit_router
from .search.routes import router as search_router
from .security.headers import SecurityHeadersMiddleware
from .services.routes import router as service_catalog_router
from .services.store import close_service_catalog_store, init_service_catalog_store
from .web import landing_router, web_router

_oauth_refresh_available = False
try:
    from .integrations.oauth_refresh import (
        start_oauth_refresh_worker,
        stop_oauth_refresh_worker,
    )
    _oauth_refresh_available = True
except ImportError:
    pass

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info("incident_copilot_starting", debug=settings.debug)
        set_app_start_time()
        await run_pending_migrations(settings=settings)

        # Log integration/config status once at startup (avoid per-request warning spam).
        logger.info(
            "integration_status",
            slack_configured=bool(settings.slack_bot_token),
            github_configured=bool(settings.github_token),
            gitlab_configured=bool(settings.gitlab_token),
            datadog_configured=bool(settings.datadog_api_key and settings.datadog_app_key),
            aws_cloudwatch_configured=bool(settings.aws_region),
            loki_configured=bool(settings.loki_url),
            redis_configured=bool(settings.redis_url),
            supabase_configured=bool(
                settings.supabase_url
                and (settings.supabase_service_role_key or settings.supabase_anon_key)
            ),
            supabase_db_enabled=bool(settings.supabase_db_enabled),
            supabase_auth_enabled=bool(settings.supabase_auth_enabled),
        )

        # Initialize metrics
        git_sha = os.environ.get("GIT_SHA")
        set_app_info(version="0.1.0", git_sha=git_sha)
        HEALTH_STATUS.labels(component="app").set(1)

        # Initialize audit store
        if settings.audit_enabled:
            audit_store.database_url = settings.database_url
            audit_store.retention_days = settings.audit_retention_days
            await audit_store.initialize()
            logger.info(
                "audit_store_initialized", retention_days=settings.audit_retention_days
            )

        await init_service_catalog_store()

        await start_oncall_handoff_scheduler(settings=settings)
        if _oauth_refresh_available:
            try:
                await start_oauth_refresh_worker()
            except Exception as e:
                logger.warning("oauth_refresh_worker_start_failed", error=str(e))

        yield

        await stop_oncall_handoff_scheduler()
        await close_service_catalog_store()
        if _oauth_refresh_available:
            await stop_oauth_refresh_worker()
        logger.info("incident_copilot_shutting_down")

    app = FastAPI(
        title="Incident Copilot",
        description="Context-aware incident copilot for on-call engineers",
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    # Prometheus metrics middleware (add first for accurate timing)
    app.add_middleware(
        PrometheusMiddleware,
        exclude_paths={"/metrics", "/", "/health"},
    )

    # CORS middleware (production-safe default)
    allow_origins = list(settings.cors_allow_origins or [])

    # Never allow wildcard CORS in production (and avoid foot-guns in debug too).
    if "*" in allow_origins:
        logger.warning("cors_wildcard_origin_ignored")
        allow_origins = [o for o in allow_origins if o != "*"]

    if not allow_origins:
        # Safe default: only allow the configured public app URL.
        allow_origins = [settings.app_url]
        # In debug, also allow common local dev origins.
        if settings.debug:
            allow_origins.extend(
                [
                    "http://localhost:8000",
                    "http://127.0.0.1:8000",
                    "http://localhost:3000",
                    "http://127.0.0.1:3000",
                ]
            )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(set(allow_origins)),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )

    # Basic security headers
    app.add_middleware(
        SecurityHeadersMiddleware,
        content_security_policy=(
            "default-src 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "script-src 'self' https://cdn.jsdelivr.net https://cdn.tailwindcss.com 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self' https://*.supabase.co"
        ),
    )

    # Audit logging middleware (if enabled)
    if settings.audit_enabled:
        app.add_middleware(
            AuditMiddleware,
            log_all_requests=settings.audit_log_all_requests,
            exclude_paths=settings.audit_exclude_paths,
        )

    # Rate limiting middleware (if enabled)
    if settings.ratelimit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            exclude_paths=settings.ratelimit_exclude_paths,
        )

    # Redirect unauthenticated browser requests to /login instead of JSON 401
    from starlette.responses import RedirectResponse

    from .web.routes import DashboardAuthRedirectError

    @app.exception_handler(DashboardAuthRedirectError)
    async def _redirect_to_login(request, exc):
        response = RedirectResponse(url="/login?session_expired=1", status_code=307)
        # Clear the auth cookie to break redirect loops
        response.delete_cookie("ic_access_token", path="/")
        return response

    # Include routers
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(memory_feedback_router)
    app.include_router(ai_feedback_router)
    app.include_router(memory_stats_router)
    app.include_router(auth_router)
    app.include_router(oauth_integrations_router)  # generic OAuth (handles all providers including PD/Slack)
    app.include_router(pagerduty_oauth_router)  # legacy PD OAuth (start route only; callback handled by generic)
    app.include_router(slack_oauth_router)  # legacy Slack OAuth (start route only; callback handled by generic)
    app.include_router(sso_router)
    app.include_router(supabase_auth_router)
    app.include_router(billing_router)
    app.include_router(webhooks_router)
    app.include_router(runbooks_router)
    app.include_router(demo_router)
    app.include_router(demo_trigger_router)
    app.include_router(analytics_router)
    app.include_router(incidents_router)
    app.include_router(pagerduty_sync_router)
    app.include_router(correlation_router)
    app.include_router(insights_router)
    app.include_router(latency_router)
    app.include_router(onboarding_router)
    app.include_router(plugins_router)
    app.include_router(postmortem_router)
    app.include_router(audit_router)
    app.include_router(ratelimit_router)
    app.include_router(email_router, prefix="/api")
    app.include_router(oncall_handoff_router)
    app.include_router(copilot_router)
    app.include_router(slack_copilot_router)
    app.include_router(teams_copilot_router)
    app.include_router(web_copilot_router)
    app.include_router(memory_advanced_router)
    app.include_router(service_catalog_router)
    app.include_router(search_router, prefix="/api")
    app.include_router(actions_router)
    app.include_router(landing_router)
    app.include_router(web_router)

    # Mount static files for web dashboard
    static_dir = Path(__file__).parent / "web" / "static"
    app.mount(
        "/dashboard/static", StaticFiles(directory=str(static_dir)), name="static"
    )

    @app.get("/")
    async def root():
        return {
            "name": "Incident Copilot",
            "version": "0.1.0",
            "status": "running",
        }

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import os

    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("src.main:app", host=host, port=port, reload=True)
