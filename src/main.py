"""Main FastAPI application for Incident Copilot."""

import os
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import (
    analytics_router,
    demo_router,
    health_router,
    insights_router,
    postmortem_router,
    runbooks_router,
    webhooks_router,
)
from .api.audit import router as audit_router
from .api.health import set_app_start_time
from .audit.middleware import AuditMiddleware
from .audit.store import audit_store
from .auth.routes import router as auth_router
from .auth.sso.routes import router as sso_router
from .billing.routes import router as billing_router
from .config import get_settings
from .metrics import HEALTH_STATUS, set_app_info
from .metrics.middleware import PrometheusMiddleware
from .ratelimit.middleware import RateLimitMiddleware
from .ratelimit.routes import router as ratelimit_router
from .web import landing_router, web_router

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

    app = FastAPI(
        title="Incident Copilot",
        description="Context-aware incident copilot for on-call engineers",
        version="0.1.0",
        debug=settings.debug,
    )

    # Prometheus metrics middleware (add first for accurate timing)
    app.add_middleware(
        PrometheusMiddleware,
        exclude_paths={"/metrics", "/", "/health"},
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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

    # Include routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(sso_router)
    app.include_router(billing_router)
    app.include_router(webhooks_router)
    app.include_router(runbooks_router)
    app.include_router(demo_router)
    app.include_router(analytics_router)
    app.include_router(insights_router)
    app.include_router(postmortem_router)
    app.include_router(audit_router)
    app.include_router(ratelimit_router)
    app.include_router(landing_router)
    app.include_router(web_router)

    # Mount static files for web dashboard
    static_dir = Path(__file__).parent / "web" / "static"
    app.mount(
        "/dashboard/static", StaticFiles(directory=str(static_dir)), name="static"
    )

    @app.on_event("startup")
    async def startup():
        logger.info("incident_copilot_starting", debug=settings.debug)
        set_app_start_time()

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

    @app.on_event("shutdown")
    async def shutdown():
        logger.info("incident_copilot_shutting_down")

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
