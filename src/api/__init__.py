"""API routes for Incident Copilot."""

from ..postmortem import postmortem_router
from .analytics import router as analytics_router
from .correlation import router as correlation_router
from .demo import router as demo_router
from .health import router as health_router
from .insights import router as insights_router
from .plugins import router as plugins_router
from .runbooks import router as runbooks_router
from .webhooks import router as webhooks_router

__all__ = [
    "webhooks_router",
    "correlation_router",
    "runbooks_router",
    "demo_router",
    "analytics_router",
    "health_router",
    "postmortem_router",
    "plugins_router",
    "insights_router",
]
