"""API routes for Incident Copilot."""

from .analytics import router as analytics_router
from .demo import router as demo_router
from .health import router as health_router
from .runbooks import router as runbooks_router
from .webhooks import router as webhooks_router

from ..postmortem import postmortem_router

__all__ = [
    "webhooks_router",
    "runbooks_router",
    "demo_router",
    "analytics_router",
    "health_router",
    "postmortem_router",
]
