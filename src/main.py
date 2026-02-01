"""Main FastAPI application for Incident Copilot."""

from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import analytics_router, demo_router, runbooks_router, webhooks_router
from .auth.routes import router as auth_router
from .billing.routes import router as billing_router
from .config import get_settings
from .web import web_router

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

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(auth_router)
    app.include_router(billing_router)
    app.include_router(webhooks_router)
    app.include_router(runbooks_router)
    app.include_router(demo_router)
    app.include_router(analytics_router)
    app.include_router(web_router)

    # Mount static files for web dashboard
    static_dir = Path(__file__).parent / "web" / "static"
    app.mount("/dashboard/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.on_event("startup")
    async def startup():
        logger.info("incident_copilot_starting", debug=settings.debug)

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
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
